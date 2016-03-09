#!/usr/bin/python
# coding=utf-8
"""
This file contains automatically generated regression tests created
by stbt auto-selftests.  These tests are intended to capture the
behaviour of functions that take images, so we can be aware of when
a change we make changes the behaviour of a function and to make it
easy to add additional example images.

NOTE: THE EXAMPLES BELOW ARE NOT NECESSARILY "CORRECT", so should
not be used as a guide to expected behaviour of the functions.
"""
# pylint: disable=line-too-long

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), '../../../tests'))

from example import *  # isort:skip pylint: disable=wildcard-import, import-error

_FRAME_CACHE = {}


def f(name):
    img = _FRAME_CACHE.get(name)
    if img is None:
        import cv2
        filename = os.path.join(os.path.dirname(__file__),
                                '../../screenshots', name)
        img = cv2.imread(filename)
        assert img is not None, "Failed to load %s" % filename
        _FRAME_CACHE[name] = img
    return img


def auto_selftest_Dialog():
    r"""
    >>> Dialog(frame=f("frame-object-with-dialog-different-background.png"))
    Dialog(is_visible=True, message=u'This set-top box is great')
    >>> Dialog(frame=f("frame-object-with-dialog.png"))
    Dialog(is_visible=True, message=u'This set-top box is great')
    >>> Dialog(frame=f("frame-object-with-dialog2.png"))
    Dialog(is_visible=True, message=u'This set-top box is fabulous')
    """
    pass


def auto_selftest_FalseyFrameObject():
    r"""
    >>> FalseyFrameObject(frame=f("frame-object-with-dialog-different-background.png"))
    FalseyFrameObject(is_visible=False)
    >>> FalseyFrameObject(frame=f("frame-object-with-dialog.png"))
    FalseyFrameObject(is_visible=False)
    >>> FalseyFrameObject(frame=f("frame-object-with-dialog2.png"))
    FalseyFrameObject(is_visible=False)
    """
    pass


def auto_selftest_TruthyFrameObject2():
    r"""
    >>> TruthyFrameObject2(frame=f("frame-object-without-dialog-different-background.png"))
    TruthyFrameObject2(is_visible=True)
    >>> TruthyFrameObject2(frame=f("frame-object-without-dialog.png"))
    TruthyFrameObject2(is_visible=True)
    """
    pass


def auto_selftest_not_a_frame_object():
    r"""
    >>> not_a_frame_object(4, f("frame-object-with-dialog-different-background.png"))
    hello 4
    True
    >>> not_a_frame_object(4, f("frame-object-with-dialog.png"))
    hello 4
    True
    >>> not_a_frame_object(4, f("frame-object-with-dialog2.png"))
    hello 4
    True
    >>> not_a_frame_object(4, f("frame-object-without-dialog-different-background.png"))
    hello 4
    True
    >>> not_a_frame_object(4, f("frame-object-without-dialog.png"))
    hello 4
    True
    >>> not_a_frame_object(2, f("frame-object-with-dialog-different-background.png"))
    hello 2
    True
    >>> not_a_frame_object(2, f("frame-object-with-dialog.png"))
    hello 2
    True
    >>> not_a_frame_object(2, f("frame-object-with-dialog2.png"))
    hello 2
    True
    >>> not_a_frame_object(2, f("frame-object-without-dialog-different-background.png"))
    hello 2
    True
    >>> not_a_frame_object(2, f("frame-object-without-dialog.png"))
    hello 2
    True
    """
    pass
