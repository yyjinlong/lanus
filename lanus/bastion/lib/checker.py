# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import logging
from dotmap import DotMap

import requests
import osmo.util as ou
from oslo_config import cfg

LOG = logging.getLogger(__name__)

intf_opts = [
    cfg.StrOpt('salt', help='bastion service interface md5 salt value.'),
    cfg.StrOpt('user_check_intf', help='user login validate api.'),
    cfg.StrOpt('totp_check_intf', help='the otp token validate api.'),
    cfg.StrOpt('user_asset_intf', help='fetch user asset info api.'),
    cfg.StrOpt('user_ldap_pass_intf', help='fetch user ldap password api.')
]

CONF = cfg.CONF
CONF.register_opts(intf_opts, 'INTF')


class Auth:

    @staticmethod
    def validate(username, password):
        url = CONF.INTF.user_check_intf
        payload = {'username': username, 'password': password}
        try:
            user_info = ou.http_handler(url, ou.HTTP.POST,  payload=payload)
        except Exception as _ex:
            LOG.error('** request validate api error: %s' % str(_ex))
            return False
        LOG.info('** user: %s validate pass, info: %s' % (username, user_info))
        return True

    @staticmethod
    def get_user_asset(username):
        """获取该用户授权的机器列表.

        返回的机器列表格式如下:
        [
            DotMap({'id': 1, 'ip': '10.10.1.1', 'port': 22, 'hostname': '1x'}),
            DotMap({'id': 2, 'ip': '10.10.1.2', 'port': 22, 'hostname': '2x'}),
            .....
        ]
        """
        asset_list = []
        url = CONF.INTF.user_asset_intf
        payload = {
            'username': username
        }
        sign = ou.parameter_sign(payload, CONF.INTF.salt)
        payload['sign'] = sign
        try:
            assets = ou.http_handler(url, ou.HTTP.POST, payload=payload)
        except Exception as _ex:
            LOG.error('** request asset api error: %s' % str(_ex))
            return asset_list
        asset_list = [DotMap(item) for item in assets if item]
        return asset_list

    @staticmethod
    def get_ldap_pass(username):
        password = ''
        url = CONF.INTF.user_ldap_pass_intf
        payload = {
            'ldap_user': username
        }
        sign = ou.parameter_sign(payload, CONF.INTF.salt)
        payload['sign'] = sign
        try:
            password = ou.http_handler(url, ou.HTTP.POST, payload=payload)
        except Exception as _ex:
            LOG.error('** request ldap password api error: %s' % str(_ex))
        return password


class Totp:

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
