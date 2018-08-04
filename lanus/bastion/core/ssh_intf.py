# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import threading
from io import StringIO

import paramiko
from oslo_log import log as logging

from lanus.util.service import LanusService

LOG = logging.getLogger(__name__)


class SSHServer(paramiko.ServerInterface):

    def __init__(self, context):
        self.context = context
        self.shell_request_event = threading.Event()
        context.change_win_size_event = threading.Event()

    def check_auth_password(self, username, password):
        hs = LanusService()
        if hs.validate(username, password):
            self.context.username = username
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, public_key):
        # NOTE(使用密码+OTP方式, 所以不需要使用公钥认证)
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_pty_request(self, channel, term, width, height,
                                  pixelwidth, pixelheight, modes):
        # NOTE(win_width and win_height in ``context`` or ``client channel``,
        # but the main usage ``context``)
        self.context.win_width = channel.win_width = width
        self.context.win_height = channel.win_height = height
        LOG.info('*** Interface check channel pty term: %s size: (%s, %s)'
                 % (term, width, height))
        return True

    def check_channel_shell_request(self, channel):
        self.shell_request_event.set()
        return True

    def check_channel_window_change_request(self, channel, width, height,
                                            pixelwidth, pixelheight):
        # NOTE(win_width and win_height in ``context`` or ``client channel``,
        # but the main usage ``context``)
        # TODO: channel感知窗口变化, 需要传到对应的channel上去改变.这里,
        #       可能导致主进程获取的窗口大小变化, 传到别的channel上.
        #       这块的事件通知机制要改。
        #       主进程感知某个channel(一个channel一个线程)窗口变化，需要事件通知
        #       到对应的channel去更新窗口大小.
        self.context.win_width = channel.win_width = width
        self.context.win_height = channel.win_height = height
        self.context.change_win_size_event.set()
        LOG.debug('*** Interface check channel window change data: (%s, %s).'
                  % (width, height))
        return True


class SSHKeyGen(object):

    @classmethod
    def rsa_key(cls):
        core_path = os.path.dirname(os.path.abspath(__file__))
        main_path = os.path.dirname(os.path.dirname(core_path))
        proj_path = os.path.dirname(main_path)
        rsa_key_path = os.path.join(proj_path, '.keys', 'rsa_key')
        if not os.path.isfile(rsa_key_path):
            cls.create_rsa_key(rsa_key_path)
        return paramiko.RSAKey(filename=rsa_key_path)

    @classmethod
    def create_rsa_key(cls, filename, length=2048, password=None):
        """ Generating private key
        """
        f = StringIO()
        prv = paramiko.RSAKey.generate(length)
        prv.write_private_key(f, password=password)
        private_key = f.getvalue()
        with open(filename, 'w') as f:
            f.write(private_key)
