from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order
import time
from contextlib import contextmanager

import numpy
import pytest

import stbt


def test_motionresult_repr():
    assert repr(stbt.MotionResult(
        time=1466002032.335607, motion=True,
        region=stbt.Region(x=321, y=32, right=334, bottom=42),
        frame=stbt.Frame(numpy.zeros((720, 1280, 3)),
                         time=1466002032.335607))) \
        == ("MotionResult("
            "time=1466002032.336, motion=True, "
            "region=Region(x=321, y=32, right=334, bottom=42), "
            "frame=<stbt.Frame(time=1466002032.336, dimensions=1280x720x3)>)")


def test_wait_for_motion_half_motion_str_2of4():
    with MockTime().patch():
        res = stbt.wait_for_motion(
            consecutive_frames='2/4', frames=fake_frames())
    print(res)
    assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_2of3():
    with MockTime().patch():
        res = stbt.wait_for_motion(
            consecutive_frames='2/3', frames=fake_frames())
    print(res)
    assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_4of10():
    with MockTime().patch():
        # Time is not affected by consecutive_frames parameter
        res = stbt.wait_for_motion(
            consecutive_frames='4/10', timeout_secs=20, frames=fake_frames())
    assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_3of4():
    try:
        with MockTime().patch():
            stbt.wait_for_motion(consecutive_frames='3/4', frames=fake_frames())
        assert False, "wait_for_motion succeeded unexpectedly"
    except stbt.MotionTimeout:
        pass


def test_wait_for_motion_half_motion_int():
    with pytest.raises(stbt.MotionTimeout), MockTime().patch():
        stbt.wait_for_motion(consecutive_frames=2, frames=fake_frames())


def fake_frames():
    a = numpy.zeros((2, 2, 3), dtype=numpy.uint8)
    a.flags.writeable = False
    b = numpy.ones((2, 2, 3), dtype=numpy.uint8) * 255
    b.flags.writeable = False

    # Motion:                 v     v     v     v     v     v     v     v     v
    data = [a, a, a, a, a, a, b, b, a, a, b, b, a, a, b, b, a, a, b, b, a, a, b]
    #       ^                 ^
    #       |                 L Motion starts here at timestamp 1466084606.
    #       L Video starts here at timestamp 1466084600

    start_time = time.time()
    for n, x in enumerate(data):
        t = start_time + n
        time.sleep(t - time.time())
        yield stbt.Frame(x, time=t)


class MockTime(object):
    def __init__(self, start_time=1466084600.):
        self._time = start_time
        self._functions = []

    def time(self):
        t = self._time
        return t

    def sleep(self, seconds):
        while self._functions and self._functions[0][0] <= self._time + seconds:
            _, fn = self._functions.pop(0)
            fn()

        self._time += seconds

    def interrupt(self, exception):
        def raise_exception():
            raise exception
        self.at(0, raise_exception)

    def at(self, offset, function):
        self._functions.append((self._time + offset, function))
        self._functions.sort()

    @contextmanager
    def assert_duration(self, seconds):
        start_time = self._time
        yield self
        assert self._time - start_time == seconds

    @contextmanager
    def patch(self):
        from mock import patch
        with patch("time.time", self.time), \
                patch("time.sleep", self.sleep):
            yield self
