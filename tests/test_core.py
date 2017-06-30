# coding: utf-8

import itertools
import sys
import time

import mock
import numpy
import pytest

from stbt import MatchResult, Region, wait_until


# pylint:disable=redefined-outer-name,unused-argument


class f(object):
    """Helper factory for wait_until selftests. Creates a callable object that
    returns the specified values one by one each time it is called.

    Values are specified as space-separated characters. `.` means `None` and
    `F` means `False`.
    """

    mapping = {".": None, "F": False}

    def __init__(self, spec):
        self.spec = spec
        self.iterator = itertools.cycle(f.mapping.get(x, x)
                                        for x in self.spec.split())

    def __repr__(self):
        return "f(%r)" % self.spec

    def __call__(self):
        time.sleep(1)
        v = next(self.iterator)
        sys.stderr.write("f() -> %s\n" % v)
        return v


@pytest.fixture(scope="function")
def mock_time():
    """Mocks out `time.time()` and `time.sleep()` so that time only advances
    when you call `time.sleep()`.
    """

    t = [1497000000]

    def _time():
        sys.stderr.write("time.time() -> %s\n" % t[0])
        return t[0]

    def _sleep(n):
        sys.stderr.write("time.sleep(%s)\n" % n)
        t[0] += n

    with mock.patch("time.time", _time), mock.patch("time.sleep", _sleep):
        yield


class Zero(object):
    def __nonzero__(self):
        return False

    def __eq__(self, other):
        return isinstance(other, Zero)


@pytest.mark.parametrize("f,kwargs,expected", [
    # wait_until returns on success
    (f(". a b"), {}, "a"),
    (f("F a b"), {}, "a"),

    # wait_until tries one last time after reaching timeout_secs
    (f("F T"), {"timeout_secs": 1}, "T"),
    (f("F T"), {"timeout_secs": 0.1}, "T"),
    (f("F F T"), {"timeout_secs": 1}, False),

    # wait_until with zero timeout tries once
    (lambda: True, {"timeout_secs": 0}, True),

    # stable_secs behaviour
    (f("a b b"), {}, "a"),
    (f("a b b"), {"stable_secs": 1}, "b"),
    (f("a b c"), {"stable_secs": 1}, None),

    # timeout_secs elapsed
    #        |   ┌ stable_secs needed
    #        v   v
    (f("a b b b b b b b b b b"), {"timeout_secs": 3, "stable_secs": 3}, None),

    # Timeout reached
    #        | ┌ stable_secs reached
    #        v v
    (f("a b b b a a a a a a a"), {"timeout_secs": 3, "stable_secs": 2}, "b"),

    # Falsey values
    (f("F F F"), {}, False),
    (f("F F F"), {"stable_secs": 1}, None),
    (Zero, {"interval_secs": 1}, Zero())
])
def test_wait_until(mock_time, f, kwargs, expected):
    assert wait_until(f, **kwargs) == expected


def test_that_wait_until_times_out(mock_time):
    assert not wait_until(Zero, interval_secs=1)
    assert time.time() == 1497000010


def test_that_wait_until_returns_first_stable_value(mock_time):

    def MR(match, x):
        time.sleep(1)  # advance the mock time by 1 second
        return MatchResult(
            time.time(), match, Region(x=x, y=0, width=10, height=2),
            first_pass_result=1,
            frame=numpy.random.randint(0, 255, (2, 2, 3), numpy.uint8),
            image="reference.png")

    def g():
        yield MR(False, x=1)
        yield MR(True, x=2)
        yield MR(True, x=3)
        yield MR(True, x=4)
        yield MR(True, x=4)
        yield MR(True, x=4)
        yield MR(True, x=4)
        yield MR(True, x=4)

    results = g()

    def match():
        return next(results)

    result = wait_until(match, stable_secs=2)
    assert result.match
    assert result.region.x == 4
    assert result.time == 1497000004
