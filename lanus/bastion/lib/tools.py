# -*- coding:utf-8 -*-
#
# Copyright @ 2019 OPS Inc.
#
# Author: Jinlong Yang
#

import lanus.util.common as cm


class Tools(object):

    def __init__(self):
        pass

    def run_ip(self, ip):
        hostname = 'l-jinlong.op.test.dx'
        node = 'com.rong.ops.credit.money'
        result = ('hostname: %s\r\n'
                  'node    : %s' % (cm.wc(hostname, False),
                                    cm.wc(node, False)))
        return result

    def run_hostname(self, hostname):
        ip = '192.168.1.33'
        node = 'com.rong.ops.daikuan.main'
        result = ('ip  : %s\r\n'
                  'node: %s' % (cm.wc(ip, False),
                                cm.wc(node, False)))
        return result
