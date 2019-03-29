#!/usr/bin/python

"""
Copyright 2012-2013 YouView TV Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import itertools
import sys

import _stbt.control
import _stbt.core
import stbt


def main(argv):
    parser = _stbt.core.argparser()
    parser.prog = 'stbt record'
    parser.description = 'Create an stb-tester test script'
    parser.add_argument(
        '--control-recorder',
        default=stbt.get_config('record', 'control_recorder'),
        help='The source of remote control keypresses (default: %(default)s)')
    parser.add_argument(
        '-o', '--output-file',
        default=stbt.get_config('record', 'output_file'),
        help='The filename of the generated script (default: %(default)s)')
    args = parser.parse_args(argv[1:])
    stbt.debug("Arguments:\n" + "\n".join([
        "%s: %s" % (k, v) for k, v in args.__dict__.items()]))

    try:
        script = open(args.output_file, 'w')
    except IOError as e:
        e.strerror = "Failed to write to output-file '%s': %s" % (
            args.output_file, e.strerror)
        raise

    with _stbt.core.new_device_under_test_from_config(args) as dut:
        record(dut, args.control_recorder, script)


def record(dut, control_recorder, script_out):
    dut.get_frame()  # Fail early if no video
    count = itertools.count(1)
    old_key = None

    def write_wait_for_match():
        if old_key is None:
            return
        filename = "%04d-%s-complete.png" % (next(count), old_key)
        stbt.save_frame(dut.get_frame(), filename)
        script_out.write("    stbt.wait_for_match('%s')\n" % filename)

    script_out.write("import stbt\n\n\n")
    script_out.write("def test_that_WRITE_TESTCASE_DESCRIPTION_HERE():\n")
    try:
        for key in _stbt.control.uri_to_control_recorder(control_recorder):
            write_wait_for_match()
            script_out.write("    stbt.press('%s')\n" % key)
            dut.press(key)
            old_key = key
    except KeyboardInterrupt:
        write_wait_for_match()
        return
    write_wait_for_match()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
