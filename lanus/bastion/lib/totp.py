# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class TOTPService(object):

    def verify(self, token):
        # NOTE(连续3次连接OTP服务失败, 则进行降级.)
        for i in range(3):
            pass
