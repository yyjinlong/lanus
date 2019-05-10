# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import re

import pyte


class IOCleaner(object):

    def __init__(self, width=180, height=80):
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)
        self.ps1_pattern = re.compile(r'^\[?.*@.*\]?[\$#]\s|mysql>\s')

    def tty_clean(self, data):
        display_list = []
        if not isinstance(data, bytes):
            data = data.encode('utf-8', errors='ignore')
        self.stream.feed(data)
        display_list = [line
                        for line in self.screen.display if line.strip()]
        self.screen.reset()
        return display_list

    def tty_input_clean(self, data):
        display_list = self.tty_clean(data)
        if display_list:
            screen_info = display_list[-1]
        else:
            screen_info = ''
        return self.ps1_pattern.sub('', screen_info)

    def tty_output_clean(self, data):
        display_list = self.tty_clean(data)
        return '\n'.join(display_list)
