# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

from dotmap import DotMap

from oslo_config import cfg
from oslo_log import log as logging

import carol.util.common as cm

LOG = logging.getLogger(__name__)

intf_opts = [
    cfg.StrOpt('salt',
               help='bastion service interface md5 salt value.'),
    cfg.StrOpt('user_valid_intf',
               help='bastion service user login validate interface.'),
    cfg.StrOpt('user_asset_intf',
               help='bastion service fetch user asset info interface.'),
    cfg.StrOpt('user_ldap_pass_intf',
               help='bastion service fetch user ldap password interface.')
]

CONF = cfg.CONF
CONF.register_opts(intf_opts, 'INTF')


class CarolService(object):

    def validate(self, username, password):
        url = CONF.INTF.user_valid_intf
        payload = {
            'username': username,
            'password': password
        }
        user_info = cm.http_handler(url, payload, 'POST')
        if user_info is None:
            return False
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
        sign = cm.parameter_sign(payload)
        payload['sign'] = sign
        assets = cm.http_handler(url, payload, 'POST')
        if assets is None:
            return asset_list
        asset_list = [DotMap(item) for item in assets if item]
        return asset_list

    def get_ldap_pass(self, username):
        url = CONF.INTF.user_ldap_pass_intf
        payload = {
            'ldap_user': username
        }
        sign = cm.parameter_sign(payload)
        payload['sign'] = sign
        password = cm.http_handler(url, payload, 'POST')
        return password
