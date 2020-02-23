# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import sys
import queue
import socket
import signal
import logging
import traceback
import multiprocessing

import paramiko
from dotmap import DotMap
from oslo_config import cfg
from osmo.base import Application

import lanus.bastion.common as cm
from lanus.bastion.sshd.interface import (
    SSHKeyGen,
    SSHServerInterface
)
from lanus.bastion.sshd.interactive import SSHInteractive

LOG = logging.getLogger(__name__)

server_opts = [
    cfg.StrOpt('host', default='0.0.0.0',
                help='lanus bastion server listen address.'),
    cfg.IntOpt('port', default=None,
                help='lanus bastion server listen port.'),
    cfg.IntOpt('pool_limit', default=None,
                help='lanus bastion server process pool size.'),
    cfg.IntOpt('session_limit', default=None,
                help='lanus bastion server session clone size.')
]

ssh_opts = [
    cfg.IntOpt('timeout', default=None,
               help='Transport accept next channel timeout.')
]

CONF = cfg.CONF
CONF.register_opts(server_opts, 'SERVER')
CONF.register_opts(ssh_opts, 'SSH')


def SignalHandler():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def SSHBootstrap(client, rhost, rport):
    # NOTE(为每一个socket进程定义一些全局属性; 每个channel线程共享.)
    context = DotMap()
    context.client = client
    context.channel_list = []
    context.remote_host = rhost

    transport = paramiko.Transport(client, gss_kex=False)
    try:
        transport.load_server_moduli()
    except:
        LOG.error('*** Failed to load moduli -- gex will be unsupported.')
        client.close()
        sys.exit(1)

    context.transport = transport
    transport.add_server_key(SSHKeyGen.rsa_key())

    ssh_server = SSHServerInterface(context)
    try:
        transport.start_server(server=ssh_server)
    except paramiko.SSHException as _ex:
        LOG.error('*** Bootstrap ssh start server failed: %s' % str(_ex))
        LOG.error(traceback.format_exc())
        client.close()
        sys.exit(1)

    while transport.is_active():
        client_channel = transport.accept(timeout=CONF.SSH.timeout)
        if client_channel is None:
            if not context.channel_list:
                LOG.error('*** Client channel timeout from host: %s.' % rhost)
                LOG.error('*** First login timeout > %s, so close client.'
                          % CONF.SSH.timeout)
                try:
                    client.send(b'Connect from %s timeout.' % rhost)
                    close_data = client.recv(1024)
                    LOG.info('*** Login timeout receive client close data: %s'
                             % close_data)
                    client.close()
                    transport.atfork()
                except:
                    pass
                sys.exit(1)
            continue

        ssh_server.shell_request_event.wait(10)
        if not ssh_server.shell_request_event.is_set():
            LOG.error('*** Client never asked for a shell.')
            try:
                client.send(b'Must be shell request.')
                close_data = client.recv(1024)
                LOG.info('*** Client not use shell receive close data: %s'
                         % close_data)
                client.close()
                transport.atfork()
            except:
                pass
            sys.exit(1)
        LOG.info('*** Client asking for a shell.')

        if (len(context.channel_list) + 1) > CONF.SERVER.session_limit:
            tip = u'超出session预定上限值! 请使用已打开的窗口, 并关闭该窗口.'
            client_channel.sendall(cm.ws(tip, 1))
            close_data = client_channel.recv(1024)
            LOG.info(b'*** Session over limit, receive data: %s' % close_data)
            client_channel.close()
            continue

        # NOTE(channel list 需要多个线程共享, 因为若某个线程(session)
        # 自动退出，需要将自己自动从该列表剔除)
        context.channel_list.append(client_channel)
        context[client_channel] = queue.Queue()

        pid = os.getpid()
        LOG.info('*** Login user: %s from (%s:%s) on pid: %s.'
                 % (context.username, rhost, rport, pid))

        # NOTE(client channel 不能多线程共享全局变量, 否则session就会乱)
        try:
            ssh_interactive = SSHInteractive(context, client_channel)
            ssh_interactive.start()
        except:
            LOG.error(traceback.format_exc())

    try:
        client.close()
    except:
        pass
    LOG.info('*** Client from %s transport.is_active() is false.' % rhost)
    sys.exit(1)


class Bastion(Application):
    name = 'bastion'
    version = '0.1'

    def __init__(self):
        super(Bastion, self).__init__()
        self.host = CONF.SERVER.host
        self.port = CONF.SERVER.port
        self.limit = CONF.SERVER.pool_limit
        self.pool = multiprocessing.Pool(self.limit, SignalHandler)

    def run(self):
        self.build_lisen()
        LOG.info('Starting ssh server at %s:%s' % (self.host, self.port))
        LOG.info('Quit the server with CONTROL-C.')

        while True:
            cs, (rhost, rport) = self.fd.accept()
            LOG.info('*** Receive client addr: %s:%s' % (rhost, rport))
            cs.setblocking(0)
            try:
                self.pool.apply_async(SSHBootstrap, (cs, rhost, rport))
            except KeyboardInterrupt:
                self.pool.terminate()
                self.pool.close()
                self.close()
            except Exception as _ex:
                self.close()
                LOG.error('*** SSH bootstrap exception: %s' % str(_ex))
                LOG.error(traceback.format_exc())

    def build_lisen(self):
        self.fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.fd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.fd.bind((self.host, self.port))
        self.fd.listen(self.limit)

    def close(self):
        try:
            self.fd.close()
        except:
            pass
