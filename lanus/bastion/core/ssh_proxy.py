# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import re
import sys
import time
import selectors
import traceback
from datetime import datetime

import paramiko
from oslo_log import log as logging
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


class SSHProxy(object):

    def __init__(self, context, client_channel):
        self.context = context
        self.username = context.username
        self.client_channel = client_channel
        self.password = LanusService().get_ldap_pass(self.username)

    def login(self, asset_info, term='xterm', width=80, height=24):
        self.ip = asset_info.ip
        self.port = asset_info.port
        width = self.client_channel.win_width
        height = self.client_channel.win_height
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
        self.write_log(channel_id, login_info)
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
        prev_cmd = ''
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
                    cmd_info.append(backend_data)
                    log_info.append(backend_data)
                else:
                    channel_id = client_channel.get_id()
                    cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        # NOTE(记录命令-清洗)
                        input_cmd = io_cleaner.input_clean(b''.join(cmd_info)).strip()
                        if input_cmd:
                            cmd_msg = '[%s] %s' % (cur_time, input_cmd)
                            self.write_cmd(channel_id, cmd_msg)
                            cmd_info.clear()
                            prev_cmd = input_cmd

                        # NOTE(记录输出-清洗)
                        if re.search('sz\s+.*', input_cmd) is not None or \
                           re.search('sz\s+.*', prev_cmd) is not None or \
                           input_cmd in ['rz', 'sl']:
                            # NOTE(sz、rz、sl等命令不记录输出)
                            log_info.clear()
                        else:
                            output_msg = io_cleaner.output_clean(b''.join(log_info))
                            self.write_log(channel_id, output_msg)
                            log_info.clear()
                            log_info.append(backend_data.lstrip(b'\r\n'))
                    except:
                        traceback.print_exc()
                        try:
                            # NOTE(记录命令-不清洗)
                            input_cmd = b''.join(cmd_info).decode('utf-8', errors='ignore')
                            cmd_msg = '[%s] %s' % (cur_time, input_cmd)
                            self.write_cmd(channel_id, cmd_msg)
                            cmd_info.clear()

                            # NOTE(记录日志-不清洗)
                            output_msg = b''.join(log_info).decode('utf-8', errors='ignore')
                            self.write_log(channel_id, output_msg)
                            log_info.clear()
                            log_info.append(backend_data.lstrip(b'\r\n'))
                        except:
                            traceback.print_exc()

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
