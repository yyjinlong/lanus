# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import os
import subprocess
from datetime import date, timedelta

from oslo_config import cfg
from osmo.base import Application

from lanus.cleaner.core.cleaner import IOCleaner

CONF = cfg.CONF

record_opts = [
    cfg.StrOpt('record_path',
                help='bastion server record operation log info.'),
    cfg.BoolOpt('is_clean_today_log',
                help='whether to wash today’s log or not.')
]

CONF = cfg.CONF
CONF.register_opts(record_opts, 'RECORD')


class LOGCleaner(Application):
    name = 'log cleaner'
    version = '0.1'

    def __init__(self):
        super(LOGCleaner, self).__init__()
        self.io_cleaner = IOCleaner()

    def run(self):
        clean_day = None
        today = date.today()
        if CONF.RECORD.is_clean_today_log:
            clean_day = today.strftime('%Y%m%d')
        else:
            clean_day = (today + timedelta(days=-1)).strftime('%Y%m%d')
        log_path = '%s/%s' % (CONF.RECORD.record_path, clean_day)
        print ('** will handle log path is: %s' % log_path)
        out = subprocess.check_output(['ls', log_path])
        log_file_list = out.decode('utf-8', errors='ignore').split('\n')
        for log_file in log_file_list:
            if log_file == '':
                continue
            self.cleaner(log_path, log_file)
        print ('** log directory: %s all log file handle finshed.' % clean_day)

    def cleaner(self, log_path, log_file):
        log_info = []
        log_file_path = '%s/%s' % (log_path, log_file)
        with open(log_file_path) as fp:
            for line in fp:
                result = self.io_cleaner.tty_output_clean(line)
                log_info.append(result)
        self.write_back(log_path, log_file, log_info)
        try:
            os.remove(log_file_path)
        except:
            pass

    def write_back(self, log_path, log_file, log_info):
        new_log_file = '%s/new_%s' % (log_path, log_file)
        with open(new_log_file, 'a') as fp:
            for data in log_info:
                fp.write(data)
                fp.write('\n')
                fp.flush()
        print ('** log file: %s handle finished.' % log_file)
