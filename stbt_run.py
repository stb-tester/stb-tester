#!/usr/bin/python3

"""
Copyright 2012-2013 YouView TV Ltd.
          2014-2022 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import argparse
import sys

import _stbt.core
from _stbt import imgproc_cache
from _stbt.config import get_config
from _stbt.logging import debug, init_logger
from _stbt.stbt_run import (load_test_function,
                            sane_unicode_and_exception_handling, video)


def main(argv):
    parser = _stbt.core.argparser()
    parser.prog = 'stbt run'
    parser.description = 'Run an stb-tester test script'
    add_arguments(parser.add_argument)
    parser.add_argument(
        'script', metavar='FILE[::TESTCASE]', help=(
            "The python test script to run. Optionally specify a python "
            "function name to run that function; otherwise only the script's "
            "top-level will be executed."))
    parser.add_argument(
        'args', nargs=argparse.REMAINDER, metavar='ARG',
        help='Additional arguments passed on to the test script (in sys.argv)')

    args = parser.parse_args(argv[1:])
    init_logger()
    debug("Arguments:\n" + "\n".join([
        "%s: %s" % (k, v) for k, v in args.__dict__.items()]))

    dut = _stbt.core.new_device_under_test_from_config(args)
    with sane_unicode_and_exception_handling(args.script), \
            video(args, dut), \
            imgproc_cache.setup_cache(filename=args.cache):
        dut.get_frame()  # wait until pipeline is rolling
        test_function = load_test_function(args.script, args.args)
        test_function.call()


def add_arguments(add_argument):
    add_argument(
        '--cache', default=imgproc_cache.default_filename,
        help="Path for image-processing cache (default: %(default)s")
    add_argument(
        '--save-screenshot', default='on-failure',
        choices=['always', 'on-failure', 'never'],
        help="Save a screenshot at the end of the test to screenshot.png")
    add_argument(
        '--save-thumbnail', default='never',
        choices=['always', 'on-failure', 'never'],
        help="Save a thumbnail at the end of the test to thumbnail.jpg")


# Pytest plugin that does the same as `main` above:

def pytest_addoption(parser):
    add_arguments(parser.addoption)
    # Arguments from `_stbt.core.argparser`:
    parser.addoption(
        '--control',
        default=get_config('global', 'control'),
        help='The remote control to control the stb (default: %(default)s)')
    parser.addoption(
        '--source-pipeline',
        default=get_config('global', 'source_pipeline'),
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.addoption(
        '--sink-pipeline',
        default=get_config('global', 'sink_pipeline'),
        help='A gstreamer pipeline to use for video output '
             '(default: %(default)s)')
    parser.addoption(
        '--save-video', help='Record video to the specified file',
        metavar='FILE', default=get_config('run', 'save_video'))


def pytest_configure(config):
    _stbt.logging._debug_level = config.option.verbose


def pytest_sessionstart(session):
    args = session.config.option
    init_logger()
    debug("Arguments:\n" + "\n".join([
        "%s: %s" % (k, v) for k, v in args.__dict__.items()]))

    dut = _stbt.core.new_device_under_test_from_config(args)
    session.dut = dut
    session.video = video(args, dut)
    session.video.__enter__()
    session.imgproc_cache = imgproc_cache.setup_cache(filename=args.cache)
    session.imgproc_cache.__enter__()
    dut.get_frame()  # wait until pipeline is rolling


def pytest_sessionfinish(session):
    session.imgproc_cache.__exit__(None, None, None)
    session.video.__exit__(None, None, None)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
