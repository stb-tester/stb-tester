#!/usr/bin/python

"""
Copyright 2012-2013 YouView TV Ltd.
          2014-2017 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import argparse
import sys

import _stbt.core
from _stbt.logging import debug
from _stbt.stbt_run import (load_test_function,
                            sane_unicode_and_exception_handling, video)


def main(argv):
    parser = _stbt.core.argparser()
    parser.prog = 'stbt run'
    parser.description = 'Run an stb-tester test script'
    parser.add_argument(
        '--save-screenshot', default='on-failure',
        choices=['always', 'on-failure', 'never'],
        help="Save a screenshot at the end of the test to screenshot.png")
    parser.add_argument(
        '--save-thumbnail', default='never',
        choices=['always', 'on-failure', 'never'],
        help="Save a thumbnail at the end of the test to thumbnail.jpg")
    parser.add_argument(
        'script', metavar='FILE[::TESTCASE]', help=(
            "The python test script to run. Optionally specify a python "
            "function name to run that function; otherwise only the script's "
            "top-level will be executed."))
    parser.add_argument(
        'args', nargs=argparse.REMAINDER, metavar='ARG',
        help='Additional arguments passed on to the test script (in sys.argv)')

    args = parser.parse_args(argv[1:])
    debug("Arguments:\n" + "\n".join([
        "%s: %s" % (k, v) for k, v in args.__dict__.items()]))

    dut = _stbt.core.new_device_under_test_from_config(args)
    with sane_unicode_and_exception_handling(args.script), video(args, dut):
        test_function = load_test_function(args.script, args.args)
        test_function.call()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
