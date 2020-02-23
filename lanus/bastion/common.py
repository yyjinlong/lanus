# -*- coding:utf-8 -*-
#
# Copyright @ 2017 OPS Inc.
#
# Author: Jinlong Yang
#

import logging
from enum import Enum, unique

from oslo_config import cfg
LOG = logging.getLogger(__name__)

intf_opts = [
    cfg.StrOpt('salt', help='bastion service interface md5 salt value.'),
]

CONF = cfg.CONF
CONF.register_opts(intf_opts, 'INTF')

# NOTE(Terminal symbol)
BELL_CHAR = b'\x07'
CLEAR_CHAR = b'\x1b[H\x1b[2J'
ENTER_CHAR = [b'\r', b'\n', b'\r\n']
BACKSPACE_CHAR = {b'\x08': b'\x08\x1b[K', b'\x7f': b'\x08\x1b[K'}
UNSUPPORT_CHAR = {b'\x01': 'Ctrl-A', b'\x05': 'Ctrl-E'}

PROMPT = 'Opt> '

BUF_SIZE = 1 * 1024 * 1024


@unique
class TimeoutResult(Enum):

    PARENT_TIMEOUT = 0
    CHILD_TIMEOUT = 1


def terminal_art():
    art = "\033[1;35m\r\n"
    art += " " * 4 + "                                           \r\n"
    art += " " * 4 + "                  _oo8oo_                  \r\n"
    art += " " * 4 + "                 o8888888o                 \r\n"
    art += " " * 4 + '                 88" . "88                 \r\n'
    art += " " * 4 + "                 (| -_- |)                 \r\n"
    art += " " * 4 + "                 0\  =  /0                 \r\n"
    art += " " * 4 + "               ___/'==='\___               \r\n"
    art += " " * 4 + "             .' \\|     |// '.             \r\n"
    art += " " * 4 + "            / \\|||  :  |||// \            \r\n"
    art += " " * 4 + "           / _||||| -:- |||||_ \           \r\n"
    art += " " * 4 + "          |   | \\\  -  /// |   |          \r\n"
    art += " " * 4 + "          | \_|  ''\---/''  |_/ |          \r\n"
    art += " " * 4 + "          \  .-\__  '-'  __/-.  /          \r\n"
    art += " " * 4 + "        ___'. .'  /--.--\  '. .'___        \r\n"
    art += " " * 4 + "     ."" '<  '.___\_<|>_/___.'  >' "".     \r\n"
    art += " " * 4 + "    | | :  `- \`.:`\ _ /`:.`/ -`  : | |    \r\n"
    art += " " * 4 + "    \  \ `-.   \_ __\ /__ _/   .-` /  /    \r\n"
    art += " " * 4 + "=====`-.____`.___ \_____/ ___.`____.-`=====\r\n"
    art += " " * 4 + "                  `=---=`                  \r\n"
    art += " " * 4 + "                                           \r\n"
    art += "\033[0m"
    tip = terminal_tip()
    return art + tip


def terminal_tip():
    art = "\033[1;31m"
    art += " " * 4 + "        佛祖保佑           永无bug         \r\n"
    art += "\033[0m\r\n"
    return art


def terminal_nav(username):
    tip = """{color}
    {username}{end} 你好, 跳板机使用方法如下:\r\n
        ➜  输入{color}ID{end} 直接登录或{color}部分IP,主机名{end}进行\
搜索登录(如果唯一).\r
        ➜  输入{color}/{end} + {color}IP, 主机名{end} 搜索, 如: /ip.\r
        ➜  输入{color}P/p{end} 显示您有权限的主机.\r
        ➜  输入{color}T/t{end} 进入常用工具集.\r
        ➜  输入{color}H/h{end} 帮助.\r
        ➜  输入{color}Q/q{end} 退出.\r
    """.format(color='\033[1;35m', username=username, end='\033[0m')
    return tip


def tools_nav():
    tips = '\r\n'
    tips += u'\033[1;35m'
    tips += u'命令执行格式如下: \r\n\r\n'
    tips += u'    ➜  输入 ip 192.168.0.121 \r\n'
    tips += u'    ➜  输入 hostname l-jinlong.ops.cn8 \r\n'
    tips += u'    ➜  输入 clear 清屏\r\n'
    tips += u'    ➜  输入 quit  退出常用工具查询模式'
    tips += u'\033[0m'
    return tips


def ws(s, before=0, after=1, level='info'):
    """Wrap string info with line feed.
    """
    tip = ''
    if level == 'info':
        tip = '\r\n' * before + s + '\r\n' * after
    elif level == 'warn':
        tip = '\r\n' * before + '\033[1;33m' + s + '\033[0m' + '\r\n' * after
    return tip


def wc(s, has_bg=True):
    """Wrap string with color.
    """
    if has_bg:
        return '\033[0;30;45m' + s + '\033[0m'
    else:
        return '\033[1;34m' + s + '\033[0m'
