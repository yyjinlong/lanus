# -*- coding:utf-8 -*-
#
# Copyright @ 2020 OPS, YY Inc.
#
# Author: Jinlong Yang
#

import osmo.util as ou
from flask import Blueprint


bp = Blueprint('v1', __name__)


@bp.route('/totp', methods=['POST'])
def totp():
    return ou.context(ou.RESULT.SUCC.value)


@bp.route('/auth', methods=['POST'])
def auth():
    ret_info = {
        'user': {
            'username': 'hello',
            'name': 'hello',
            'email': 'hello@xx.com'
        }
    }
    return ou.context(ou.RESULT.SUCC.value, data=ret_info)


@bp.route('/asset', methods=['POST'])
def asset():
    asset_list = [
        {'id': 1, 'ip': '10.12.16.248', 'port': 50022, 'hostname': 'hello00'}
    ]
    return ou.context(ou.RESULT.SUCC.value, data=asset_list)


@bp.route('/ldap/pass', methods=['POST'])
def ldap_pass():
    password = 'yangjinlong@163.com'
    return ou.context(ou.RESULT.SUCC.value, data=password)
