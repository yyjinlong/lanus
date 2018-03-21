# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import sys
import time
import threading
import traceback

from oslo_log import log as logging
from oslo_config import cfg

import carol.util.common as cm
from carol.util.service import CarolService
from carol.bastion.core.ssh_proxy import SSHProxy

LOG = logging.getLogger(__name__)

idle_opts = [
    cfg.IntOpt(
        'timeout',
        help='Noting to do timeout.'
    )
]

CONF = cfg.CONF
CONF.register_opts(idle_opts, 'IDLE')


class SSHJump(threading.Thread):

    def __init__(self, context, client_channel):
        super(SSHJump, self).__init__()
        self.context = context
        self.client = context.client
        self.username = context.username
        self.client_channel = client_channel
        self.assets = CarolService().get_user_asset(self.username)

    def run(self):
        self.display_banner()

        while True:
            self.client_channel.sendall(cm.ws(cm.PROMPT, 1, 0))
            try:
                self.option_handler()
            except:
                traceback.print_exc()
                self.exception_handle()
                break

    def display_banner(self):
        art = cm.terminal_art()
        nav = cm.terminal_nav(self.username)
        self.client_channel.sendall(cm.CLEAR_CHAR)
        self.client_channel.sendall(art + nav)

    def option_handler(self):
        option = self.readline()
        if option in ['p', 'P']:
            self.show_hostlist()
        elif option.startswith('/'):
            self.show_searchinfo(option)
        elif option in ['h', 'H']:
            self.display_banner()
        elif option in ['q', 'Q']:
            self.logout()
            sys.exit(1)
        else:
            search_result = self.search_asset(option)
            if len(search_result) == 1:
                self.redirect_ssh_proxy(search_result[0])
            elif len(search_result) == 0:
                self.client_channel.sendall(cm.ws(
                    'No asset match, please input again', level='warn'))
            else:
                self.client_channel.sendall(cm.ws(
                    'Search result not unique, select below or search again',
                    after=2, level='warn'))
                self.show_hostlist()

    def show_hostlist(self):
        self.show_asset_table(self.assets)

    def show_asset_table(self, asset_list):
        line = '[%-4s] %-20s %-15s %-30s'
        self.client_channel.sendall(cm.ws(
            cm.wc(line % ('ID', 'IP', 'Port', 'Hostname'))))
        for index, item in enumerate(asset_list):
            self.client_channel.sendall(cm.ws(cm.wc(
                    line % (index, item.ip, item.port, item.hostname), False)))

    def show_searchinfo(self, option):
        option = option.lstrip('/').strip().lower()
        search_result = self.search_asset(option)
        self.show_asset_table(search_result)

    def search_asset(self, option):
        if option:
            search_result = []
            # NOTE(按id方式搜索)
            if option.isdigit() and int(option) < len(self.assets):
                search_result = [self.assets[int(option)]]
            else:
                # NOTE(按ip/hostname匹配搜索)
                search_result = [
                    asset for asset in self.assets if option in asset.ip
                ] or [
                    asset for asset in self.assets
                    if option in asset.hostname.lower()
                ]
            return search_result
        return self.assets

    def redirect_ssh_proxy(self, asset_info):
        ssh_proxy = SSHProxy(self.context, self.client_channel)
        ssh_proxy.login(asset_info)

    def logout(self):
        self.exception_handle()
        remote_host = self.context.remote_host
        LOG.info('Logout relay from %s:%s' % (remote_host, self.username))

    def readline(self):
        """ Read one line data from the stream.

        This method is a coroutine which reads one line, ending in
        ``'\n'``.

        If EOF is received before ``'\n'`` is found, the partial
        line is returned. If EOF is received and the receive buffer
        is empty, an empty bytes or str object is returned.
        """
        input_data = []
        timeout = CONF.IDLE.timeout
        begin_time = int(time.time())
        while True:
            data = self.client_channel.recv(1024)

            # NOTE(超时处理)
            cur_time = int(time.time())
            if (cur_time - begin_time) > timeout:
                LOG.info('*** User: %s idle timeout > %s.'
                         % (self.username, timeout))
                self.timeout_handle()
                self.exception_handle()
                sys.exit(1)

            # NOTE(客户端关闭)
            if 0 == len(data):
                LOG.info('*** Interactive client from user: %s input data '
                         'is 0, so exit.' % (self.username))
                self.exception_handle()
                sys.exit(1)

            # NOTE(上下键及不支持的键)
            if data.startswith(b'\x1b') or data in cm.UNSUPPORT_CHAR:
                self.client_channel.sendall('')
                continue

            # NOTE(Ctrl-L 清屏)
            if data.startswith(b'\x0c'):
                self.client_channel.sendall(cm.CLEAR_CHAR)
                self.client_channel.sendall(cm.ws(cm.PROMPT, 1, 0))
                continue

            # NOTE(Ctrl-U 清行)
            if data.startswith(b'\x15'):
                clear_line_char = cm.BACKSPACE_CHAR[b'\x7f']
                for i in range(len(input_data)):
                    self.client_channel.sendall(clear_line_char)
                input_data.clear()
                continue

            # NOTE(删除符)
            if data in cm.BACKSPACE_CHAR:
                if len(input_data) > 0:
                    data = cm.BACKSPACE_CHAR[data]
                    input_data.pop()
                else:
                    data = cm.BELL_CHAR
                self.client_channel.sendall(data)
                continue

            # NOTE(回车符转到相应处理函数)
            if data in cm.ENTER_CHAR:
                self.client_channel.sendall(cm.ws('', after=2))
                option = b''.join(input_data).strip().decode()
                return option

            try:
                # NOTE(终端关闭或连接断开, 此时send会有异常)
                self.client_channel.sendall(data)
            except:
                pass
            input_data.append(data)

    def timeout_handle(self):
        tips = '\033[1;31mLogout\r\n'
        tips += ('Noting to do, timeout %s seconds, so disconnect.\033[0m'
                 % CONF.IDLE.timeout)
        self.client_channel.sendall('\r\n' + tips + '\r\n')
        LOG.warn('*** User %s idle timeout, so disconnect.' % self.username)

    def exception_handle(self):
        if self.client_channel == self.context.channel_list[0]:
            for channel in self.context.channel_list:
                channel.close()
            self.context.transport.atfork()
            self.client.close()
        else:
            if self.client_channel in self.context.channel_list:
                self.context.channel_list.remove(self.client_channel)
            self.client_channel.close()
