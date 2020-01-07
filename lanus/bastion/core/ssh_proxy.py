# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import re
import sys
import copy
import time
import logging
import selectors
import traceback
from datetime import datetime
from multiprocessing.dummy import (
    Pool as ThreadPool
)

import paramiko
from oslo_config import cfg

import lanus.util.common as cm
from lanus.bastion.lib.service import LanusService
from lanus.bastion.lib.cleaner import IOCleaner

LOG = logging.getLogger(__name__)

idle_opts = [
    cfg.IntOpt(
        'timeout',
        help='Noting to do timeout.'
    )
]

record_opts = [
    cfg.StrOpt(
        'record_path',
        help='record operation log path.'
    )
]

CONF = cfg.CONF
CONF.register_opts(idle_opts, 'IDLE')
CONF.register_opts(record_opts, 'RECORD')


class SSHProxy:

    def __init__(self, context, client_channel):
        self.context = context
        self.username = context.username
        self.client_channel = client_channel
        self.password = LanusService().get_ldap_pass(self.username)
        self.pool = ThreadPool(4)

    def login(self, asset_info, term='xterm', width=80, height=24):
        self.ip = asset_info.ip
        self.port = asset_info.port
        self.screen = ScreenCAP(self.username, self.ip)
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
            ssh_client.connect(self.ip, port=self.port, username=self.username,
                               password=self.password, allow_agent=True,
                               look_for_keys=False, compress=True, timeout=120)
        except Exception as _ex:
            msg = 'Connect host: %s failed: %s' % (self.ip, str(_ex))
            LOG.error(msg)
            self.client_channel.sendall(cm.ws(msg, level='warn'))
            return False
        channel_id = self.client_channel.get_id()
        remote_host = self.context.remote_host
        login_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        login_info = ('This Login: %s form %s' % (login_time, remote_host))
        self.screen.write_log(channel_id, login_info)
        LOG.info('*** User: %s connected to host: %s success.'
                 % (self.username, self.ip))
        backend_channel = ssh_client.invoke_shell(
            term=term, width=width, height=height)
        backend_channel.settimeout(100)
        self.interactive_shell(backend_channel)
        return True

    def interactive_shell(self, backend_channel):
        cmd_info = []
        log_info = []
        is_input_status = True
        begin_time = None
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
                cmd_info.append(client_data)
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
                    log_info.append(backend_data)
                else:
                    channel_id = client_channel.get_id()
                    self.pool.apply_async(
                        self.screen.record, (channel_id, io_cleaner,
                                             copy.copy(cmd_info),
                                             copy.copy(log_info))
                    )
                    cmd_info.clear()
                    log_info.clear()
                    log_info.append(backend_data.lstrip(b'\r\n'))

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


class ScreenCAP:

    def __init__(self, username, ip):
        self.username = username
        self.ip = ip
        self.prev_cmd = ''

    def record(self, channel_id, io_cleaner, cmd_info, log_info):
        self.io_cleaner = io_cleaner
        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self._record_all(channel_id, cmd_info, log_info, cur_time)
        except:
            LOG.error(traceback.format_exc())
            self._record_raw(log_info, channel_id, cur_time)

    def _record_all(self, channel_id, cmd_info, log_info, cur_time):
        # NOTE(jinlong): 判断client_channel获取的输入是否包含sz、rz.
        client_cmd = self.io_cleaner.input_clean(b''.join(cmd_info)).strip()
        if self.prev_cmd and self.is_rzsz(self.prev_cmd, self.prev_cmd) and \
           self.is_rzsz_end(client_cmd):
            LOG.info('** End rz/sz because input cmd: %s' % client_cmd)
            self.prev_cmd = ''

        if self.is_rzsz(client_cmd, self.prev_cmd):
            self._record_cmd(log_info, channel_id, cur_time)
            if self.is_rzsz(client_cmd, client_cmd):
                self.prev_cmd = client_cmd
            log_info.clear()
            return


        self._record_cmd(log_info, channel_id, cur_time)
        self._record_log(log_info, channel_id, cur_time)
        log_info.clear()

    def _record_cmd(self, log_info, channel_id, cur_time):
        """ 命令记录-清洗
        """
        input_cmd = self.io_cleaner.input_clean(b''.join(log_info)).strip()
        if input_cmd:
            cmd_msg = '[%s] %s' % (cur_time, input_cmd)
            self.write_cmd(channel_id, cmd_msg)

    def _record_log(self, log_info, channel_id, cur_time):
        """ 日志记录-清洗
        """
        output_msg = self.io_cleaner.output_clean(b''.join(log_info))
        self.write_log(channel_id, output_msg)

    def _record_raw(self, log_info, channel_id, cur_time):
        """ 原始日志记录-未清洗
        """
        try:
            output_msg = b''.join(log_info).decode('utf-8', errors='ignore')
            self.write_log(channel_id, output_msg)
            log_info.clear()
        except:
            LOG.error(traceback.format_exc())

    def write_log(self, channel_id, operation_info):
        self._write(channel_id, 'log', operation_info)

    def write_cmd(self, channel_id, operation_info):
        self._write(channel_id, 'cmd', operation_info)

    def _write(self, channel_id, log_type, operation_info):
        cur_time = datetime.now()
        today = cur_time.strftime('%Y%m%d')
        record_path = '%s/%s' % (CONF.RECORD.record_path, today)
        if not os.path.isdir(record_path):
            os.mkdir(record_path)
        record_file = '%s/%s_%s_%s.%s' % (record_path, self.ip,
                                          self.username, channel_id, log_type)
        with open(record_file, 'a') as fp:
            fp.write(operation_info)
            fp.write('\n')
            fp.flush()

    def is_rzsz(self, input_cmd, prev_cmd):
        if re.search('sz\s*.*', input_cmd) is not None or \
           re.search('sz\s*.*', prev_cmd) is not None or \
           re.search('rz\s*', input_cmd) is not None or \
           re.search('rz\s*', prev_cmd) is not None or \
           input_cmd in ['rz', 'sl']:
            return True
        return False

    def is_rzsz_end(self, input_cmd):
        r = re.search('\w*\s*\w*', input_cmd)
        return False if not r else r.group() == input_cmd
