# coding: utf-8

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

from textwrap import dedent

try:
    from unittest import mock
except ImportError:
    import mock  # Python 2 backport

import stbt_core


def test_multipress():
    out = []

    def press(key, interpress_delay_secs=None):  # pylint:disable=unused-argument
        out.append("press('%s')" % (key,))

    def sleep(t):
        out.append("sleep(%s)" % (t,))

    with mock.patch("stbt_core.press", press), mock.patch("time.sleep", sleep):
        multipress = stbt_core.MultiPress({"KEY_1": "@1.,-_"})
        multipress.enter_text("abc42@eXaMpLe.com")

    expected = dedent("""\
        press('KEY_2')  # a
        sleep(1)
        press('KEY_2')  # b
        press('KEY_2')
        sleep(1)
        press('KEY_2')  # c
        press('KEY_2')
        press('KEY_2')
        press('KEY_4')  # 4
        press('KEY_4')
        press('KEY_4')
        press('KEY_4')
        press('KEY_2')  # 2
        press('KEY_2')
        press('KEY_2')
        press('KEY_2')
        press('KEY_1')  # @
        press('KEY_3')  # e
        press('KEY_3')
        press('KEY_9')  # x
        press('KEY_9')
        press('KEY_2')  # a
        press('KEY_6')  # m
        press('KEY_7')  # p
        press('KEY_5')  # l
        press('KEY_5')
        press('KEY_5')
        press('KEY_3')  # e
        press('KEY_3')
        press('KEY_1')  # .
        press('KEY_1')
        press('KEY_1')
        press('KEY_2')  # c
        press('KEY_2')
        press('KEY_2')
        press('KEY_6')  # o
        press('KEY_6')
        press('KEY_6')
        sleep(1)
        press('KEY_6')  # m """)
    assert [x.split("#")[0].strip() for x in expected.split("\n")] == out
