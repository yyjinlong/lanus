# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import re

import pyte


class IOCleaner:

    def __init__(self, width=167, height=33):
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)
        self.ps1_pattern = re.compile(r'^\[?.*@.*\]?[\$#]\s|mysql>\s')

    def _clean(self, data):
        display_list = []
        if not isinstance(data, bytes):
            data = data.encode('utf-8', errors='ignore')
        self.stream.feed(data)
        display_list = [line.strip('\r\n').strip('\n')
                        for line in self.screen.display if line.strip()]
        self.screen.reset()
        return display_list

    def output_clean(self, data):
        display_list = self._clean(data)
        return '\n'.join(display_list)

    def input_clean(self, data):
        display_list = self._clean(data)
        if display_list:
            screen_info = display_list[-1]
        else:
            screen_info = ''
        return self.ps1_pattern.sub('', screen_info).strip()
