# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import sys
import copy
import time
import queue
import logging
import hashlib
import selectors
import threading
import traceback
from datetime import datetime

import paramiko
from oslo_config import cfg

import lanus.bastion.common as cm
from lanus.bastion.lib.checker import Auth
from lanus.bastion.lib.cleaner import IOCleaner

LOG = logging.getLogger(__name__)

idle_opts = [
    cfg.IntOpt('timeout', help='Noting to do timeout.')
]

record_opts = [
    cfg.StrOpt('record_path', help='record operation log path.')
]

CONF = cfg.CONF
CONF.register_opts(idle_opts, 'IDLE')
CONF.register_opts(record_opts, 'RECORD')


class SSHProxy:

    def __init__(self, context, client_channel):
        self.context = context
        self.username = context.username
        self.client_channel = client_channel
        self.password = Auth().get_ldap_pass(self.username)
        self.pipe = queue.Queue()

    def login(self, asset_info, term='xterm', width=167, height=33):
        self.ip = asset_info.ip
        self.port = asset_info.port

        # NOTE: 单线程慢慢处理屏幕记录; 原因: 多线程有问题;
        screen = ScreenCAP(self.username, self.ip, self.pipe)
        screen.start()

        try:
            width = self.client_channel.win_width
            height = self.client_channel.win_height
        except:
            pass
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client_channel.sendall(
            cm.ws('Connecting to %s@%s, please wait....\r\n' % (
                self.username, self.ip)))
        try:
            ssh_client.connect(self.ip,
                               port=self.port,
                               username=self.username,
                               password=self.password,
                               allow_agent=True,
                               look_for_keys=False, compress=True, timeout=120)
        except Exception as _ex:
            msg = 'Connect host: %s failed: %s' % (self.ip, str(_ex))
            self.client_channel.sendall(cm.ws(msg, level='warn'))
            return False
        LOG.info('** User: %s connect to host: %s success.' % (self.username,
                                                               self.ip))
        backend_channel = ssh_client.invoke_shell(term=term,
                                                  width=width,
                                                  height=height)
        backend_channel.settimeout(100)
        self.interactive_shell(backend_channel)
        return True

    def interactive_shell(self, backend_channel):
        log_info = []
        cmd_info = []
        begin_time = None
        is_input_status = True
        is_first_input = True

        client = self.context.client
        client_channel = self.client_channel
        io_cleaner = IOCleaner(client_channel.win_width,
                               client_channel.win_height)

        sel = selectors.DefaultSelector()
        sel.register(client, selectors.EVENT_READ)
        sel.register(client_channel, selectors.EVENT_READ)
        sel.register(backend_channel, selectors.EVENT_READ)

        while True:
            events = sel.select(CONF.IDLE.timeout)
            fd_sets = [key.fileobj for key, mask in events if key]
            # NOTE(SecureCrt events return [])
            if not fd_sets:
                result = self.timeout_handle(client_channel, backend_channel)
                if result == cm.TimeoutResult.PARENT_TIMEOUT.value:
                    # NOTE(主session超时, 则退到交互式界面.)
                    return
                sys.exit(1)

            # NOTE(Iterm2 events return [client事件])
            if client_channel in fd_sets or backend_channel in fd_sets:
                begin_time = int(time.time())
            cur_time = int(time.time())
            if (cur_time - begin_time) > CONF.IDLE.timeout:
                result = self.timeout_handle(client_channel, backend_channel)
                if result == cm.TimeoutResult.PARENT_TIMEOUT.value:
                    # NOTE(主session超时, 则退到交互式界面.)
                    return
                sys.exit(1)

            try:
                change_data = self.context[self.client_channel].get_nowait()
                width = change_data.get('width')
                height = change_data.get('height')
                LOG.debug('*** Proxy fetch channel: %s window change size: '
                          '(%s, %s).' % (self.client_channel, width, height))
                if backend_channel:
                    backend_channel.resize_pty(width=width, height=height)
            except:
                pass

            if client_channel in fd_sets:
                is_input_status = True
                client_data = client_channel.recv(cm.BUF_SIZE)
                if len(client_data) == 0:
                    LOG.warn('*** Proxy receive client from user: %s data '
                             'length is 0, so exit.' % self.username)
                    self.exception_handle(backend_channel)
                    sys.exit(1)
                if client_data in cm.ENTER_CHAR:
                    is_input_status = False
                backend_channel.sendall(client_data)

            if backend_channel in fd_sets:
                backend_data = backend_channel.recv(cm.BUF_SIZE)
                if len(backend_data) == 0:
                    client_channel.sendall(cm.ws(
                        'Disconnect from %s' % self.ip))
                    LOG.info('*** Logout from user: %s on host: %s.'
                             % (self.username, self.ip))
                    # NOTE(退出该机器, 不能执行sys.exit(1)终止该线程,
                    #      而是再次回到线程中等待下一次用户的输入)
                    self.logout_handle(backend_channel)
                    return

                if is_input_status:
                    # step1: 以下记录本次命令的输入.
                    if is_first_input and log_info:
                        log_info.append(self.preset_timestamp())
                        is_first_input = False
                    log_info.append(backend_data)
                    cmd_info.append(backend_data)

                else:
                    is_first_input = True
                    user_input_cmd = io_cleaner.input_clean(b''.join(cmd_info))

                    channel_id = client_channel.get_id()
                    # NOTE: 此时的log_info为: 上一次的输出 + 本次的输入.
                    self.pipe.put((channel_id,
                                   io_cleaner,
                                   user_input_cmd,
                                   copy.copy(log_info)))
                    log_info.clear()

                    # step2: 以下记录本次命令的输出.
                    log_info.append(backend_data.lstrip(b'\r\n'))
                    cmd_info.clear()

                client_channel.sendall(backend_data)
                time.sleep(paramiko.common.io_sleep)

    def timeout_handle(self, client_channel, backend_channel):
        tips = '\033[1;31mLogout\r\n'
        tips += ('Noting to do, timeout %s seconds, so disconnect.\033[0m'
                 % CONF.IDLE.timeout)
        client_channel.sendall('\r\n' + tips + '\r\n')
        LOG.warn('*** User %s on host %s %s' % (self.username, self.ip, tips))
        if client_channel == self.context.channel_list[0]:
            try:
                backend_channel.close()
            except:
                pass
            self.context.channel_list.remove(client_channel)
            result = cm.TimeoutResult.PARENT_TIMEOUT.value
        else:
            if client_channel in self.context.channel_list:
                self.context.channel_list.remove(client_channel)
            try:
                client_channel.close()
                backend_channel.close()
            except:
                pass
            result = cm.TimeoutResult.CHILD_TIMEOUT.value
        return result

    def exception_handle(self, backend_channel=None):
        if self.client_channel == self.context.channel_list[0]:
            for chan in self.context.channel_list:
                chan.close()
            self.context.transport.atfork()
        else:
            if self.client_channel in self.context.channel_list:
                self.context.channel_list.remove(self.client_channel)
            self.client_channel.close()
        if backend_channel:
            try:
                backend_channel.close()
            except:
                pass

    def logout_handle(self, backend_channel):
        try:
            backend_channel.close()
        except:
            pass

    def preset_timestamp(self):
        uuid = hashlib.md5(b'lanus+bastion').hexdigest()
        oper_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        oper_at_str = '[Command][%(uuid)s][%(time)s] ' % {'uuid': uuid,
                                                          'time': oper_at}
        return oper_at_str.encode('utf-8')


class ScreenCAP(threading.Thread):

    def __init__(self, username, ip, pipe):
        super(ScreenCAP, self).__init__()
        self.username = username
        self.ip = ip
        self.pipe = pipe

    def run(self):
        while True:
            data = self.pipe.get()
            self.record(*data)

    def record(self, channel_id, io_cleaner, user_input_cmd, log_info):
        self.io_cleaner = io_cleaner
        try:
            self._record_cmd(user_input_cmd, channel_id)
            self._record_log(log_info, channel_id)
        except:
            LOG.error(traceback.format_exc())
        log_info.clear()

    def _record_cmd(self, user_input_cmd, channel_id):
        """命令记录
        """
        if user_input_cmd:
            oper_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            input_msg = '[%s] %s' % (oper_at, user_input_cmd)
            self._write(channel_id, input_msg, 'cmd')

    def _record_log(self, log_info, channel_id):
        """日志记录-清洗
        """
        output_msg = self.io_cleaner.output_clean(b''.join(log_info))
        self._write(channel_id, output_msg)

    def _write(self, channel_id, content, log_type='log'):
        today = datetime.now().strftime('%Y%m%d')
        record_path = '%s/%s' % (CONF.RECORD.record_path, today)
        if not os.path.isdir(record_path):
            os.mkdir(record_path)
        record_file = '%s/%s_%s_%s.%s' % (record_path, self.ip,
                                          self.username, channel_id, log_type)
        with open(record_file, 'a') as fp:
            fp.write(content)
            fp.write('\n')
            fp.flush()
