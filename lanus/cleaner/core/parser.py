# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import re

import pyte


class SSHIOParser(object):

    def __init__(self, width=175, height=40):
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)
        self.ps1_pattern = re.compile(r'^\[?.*@.*\]?[\$#]\s|mysql>\s')

    def tty_parser(self, data):
        display_list = []
        if not isinstance(data, bytes):
            data = data.encode('utf-8', errors='ignore')
        try:
            self.stream.feed(data)
            display_list = [line
                            for line in self.screen.display if line.strip()]
            self.screen.reset()
        except Exception as _ex:
            print ('** tty parser log error: %s' % str(_ex))
        return display_list

    def tty_input_parser(self, data):
        display_list = self.tty_parser(data)
        if display_list:
            screen_info = display_list[-1]
        else:
            screen_info = ''
        return self.ps1_pattern.sub('', screen_info)

    def tty_output_parser(self, data):
        display_list = self.tty_parser(data)
        return '\n'.join(display_list)
