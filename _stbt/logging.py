# coding: utf-8

import argparse
import itertools
import json
import os
import sys
from collections import OrderedDict
from contextlib import contextmanager

import cv2
import numpy

from .config import get_config
from .gst_utils import numpy_from_sample
from .utils import mkdir_p

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


class LogCtx(object):
    _ctx_number = itertools.count(1)

    def __init__(self, name, data=None):
        self.data = {name: {}}
        self.frame_number = LogCtx._ctx_number.next()
        self.name = name
        self.outdir = None

        if get_debug_level() <= 1:
            return

        try:
            outdir = os.path.join("stbt-debug", self.name, "%05d" % self.frame_number)
            mkdir_p(outdir)
            self.outdir = outdir
        except OSError:
            warn("Failed to create directory '%s'; won't save debug images."
                 % d)

        if data is not None:
            self.log(data)

    def log(self, data):
        if self.outdir is None:
            return
        for k, v in data.iteritems():
            if k in self.data[self.name]:
                raise ValueError("'%s' already logged" % k)
            try:
                with numpy_from_sample(v, readonly=True) as img:
                    outname = os.path.join(self.outdir, k + ".png")
                    cv2.imwrite(outname, img)
                    self.data[self.name][k] = {
                        "filename": k + '.png',
                        "size": [img.shape[1], img.shape[0]]}
            except TypeError:
                self.data[self.name][k] = v

    def write(self):
        if self.outdir is not None:
            with open(os.path.join(self.outdir, "log.json"), 'w') as f:
                json.dump(self.data, f)


def test_that_debug_can_write_unicode_strings():
    def test(level):
        with scoped_debug_level(level):
            warn(u'Prüfungs Debug-Unicode')
            debug(u'Prüfungs Debug-Unicode')
            ddebug(u'Prüfungs Debug-Unicode')
    for level in [0, 1, 2]:
        yield (test, level)
