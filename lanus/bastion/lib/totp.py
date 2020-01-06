# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import logging

import requests
from oslo_config import cfg

LOG = logging.getLogger(__name__)

intf_opts = [
    cfg.StrOpt('totp_check_intf',
               help='bastion service otp token validate interface.'),
]

CONF = cfg.CONF
CONF.register_opts(intf_opts, 'INTF')


class TOTPService(object):

    def verify(self, username, token):
        if len(token) != 6:
            LOG.error('** token must be 6 bit.')
            return False
        if not token.isdigit():
            LOG.error('** token must be number.')
            return False
        return self.strategy(token)

    def strategy(self, username, token):
        is_demote = False
        for i in range(3):
            # NOTE(连续3次连接OTP服务失败, 则进行降级.)
            try:
                url = CONF.INTF.totp_check_intf
                payload = {'username': username, 'token': token}
                resp = requests.post(url, data=payload)
            except Exception as _ex:
                LOG.error('** Connect to otp serivce failed: %s' % str(_ex))
                is_demote = True
                continue
            http_code = resp.status_code
            if http_code != 200:
                LOG.error('** Get interface status code is: %s' % http_code)
                is_demote = True
                continue
            ret_info = resp.json()
            if ret_info.get('errcode') != 0:
                errmsg = ret_info.get('msg')
                LOG.error('** Request interface verify failed: %s' % errmsg)
                is_demote = True
                continue
            return ret_info.get('data')
        if is_demote:
            # NOTE(降级, 不再进行6位数校验, 直接返回成功.)
            LOG.warn('** Otp service is not available, need to downgrade.')
            return True
