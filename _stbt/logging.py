# coding: utf-8

import argparse
import os
import sys
from contextlib import contextmanager

from .config import get_config

_debug_level = None


def debug(msg):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if get_debug_level() > 0:
        sys.stderr.write(
            "%s: %s\n" % (os.path.basename(sys.argv[0]), msg))


def ddebug(s):
    """Extra verbose debug for stbt developers, not end users"""
    if get_debug_level() > 1:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), s))


def warn(s):
    sys.stderr.write("%s: warning: %s\n" % (
        os.path.basename(sys.argv[0]), s))


def get_debug_level():
    global _debug_level
    if _debug_level is None:
        _debug_level = get_config('global', 'verbose', type_=int)
    return _debug_level


@contextmanager
def scoped_debug_level(level):
    global _debug_level
    oldlevel = _debug_level
    _debug_level = level
    try:
        yield
    finally:
        _debug_level = oldlevel


def argparser_add_verbose_argument(argparser):
    class IncreaseDebugLevel(argparse.Action):
        num_calls = 0

        def __call__(self, parser, namespace, values, option_string=None):
            global _debug_level
            self.num_calls += 1
            _debug_level = self.num_calls
            setattr(namespace, self.dest, _debug_level)

    argparser.add_argument(
        '-v', '--verbose', action=IncreaseDebugLevel, nargs=0,
        default=get_debug_level(),  # for stbt-run arguments dump
        help='Enable debug output (specify twice to enable GStreamer element '
             'dumps to ./stbt-debug directory)')

    argparser.add_argument(
        '--structured-logging', metavar="FILENAME", default=None,
        help="Writes structed logging data to given filename.  The format of "
             "the data is newline delimited JSON objects with xz compression "
             "applied")


def test_that_debug_can_write_unicode_strings():
    def test(level):
        with scoped_debug_level(level):
            warn(u'Prüfungs Debug-Unicode')
            debug(u'Prüfungs Debug-Unicode')
            ddebug(u'Prüfungs Debug-Unicode')
    for level in [0, 1, 2]:
        yield (test, level)
