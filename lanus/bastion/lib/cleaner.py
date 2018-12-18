# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import pyte
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class IOCleaner(object):

    def __init__(self, width=175, height=40):
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)

    def clean(self, data):
        display_list = []
        if not isinstance(data, bytes):
            data = data.encode('utf-8', errors='ignore')
        try:
            self.stream.feed(data)
            display_list = [line.strip('\r\n').strip('\n')
                            for line in self.screen.display if line.strip()]
            self.screen.reset()
        except Exception as _ex:
            LOG.warn('** Clean operation log info exception: %s' % str(_ex))
            return data.decode('utf-8', errors='ignore')
        return '\n'.join(display_list)
