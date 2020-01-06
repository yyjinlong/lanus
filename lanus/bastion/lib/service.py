# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import logging
from dotmap import DotMap

import osmo.util as ou
from oslo_config import cfg

LOG = logging.getLogger(__name__)

intf_opts = [
    cfg.StrOpt('salt',
               help='bastion service interface md5 salt value.'),
    cfg.StrOpt('user_check_intf',
               help='bastion service user login validate interface.'),
    cfg.StrOpt('user_asset_intf',
               help='bastion service fetch user asset info interface.'),
    cfg.StrOpt('user_ldap_pass_intf',
               help='bastion service fetch user ldap password interface.')
]

CONF = cfg.CONF
CONF.register_opts(intf_opts, 'INTF')


class LanusService:

    def validate(self, username, password):
        url = CONF.INTF.user_check_intf
        payload = {
            'username': username,
            'password': password
        }
        try:
            user_info = ou.http_handler(url, ou.HTTP.POST,  payload=payload)
        except Exception as _ex:
            LOG.error('** request validate api error: %s' % str(_ex))
            return False
        LOG.info('** user: %s validate pass, info: %s' % (username, user_info))
        return True

    def get_user_asset(self, username):
        """ To obtain a list of user authorization machine.

        Return machine list format as follows:
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

    def get_ldap_pass(self, username):
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
