# coding: utf-8

import itertools
import os
import sys
import time

import cv2
import mock
import numpy
import pytest

import stbt
from stbt import wait_until


# pylint:disable=redefined-outer-name,unused-argument


def test_that_load_image_looks_in_callers_directory():
    # See also the test with the same name in
    # ./subdirectory/test_load_image_from_subdirectory.py
    assert numpy.array_equal(
        stbt.load_image("videotestsrc-redblue.png"),
        cv2.imread(os.path.join(os.path.dirname(__file__),
                                "videotestsrc-redblue.png")))

    with pytest.raises(IOError):
        stbt.load_image("info2.png")


def test_load_image_with_unicode_filename():
    print sys.getfilesystemencoding()
    assert stbt.load_image("Röthlisberger.png") is not None
    assert stbt.load_image(u"Röthlisberger.png") is not None
    assert stbt.load_image(u"R\xf6thlisberger.png") is not None


class C(object):
    """A class with a single property, used by the tests."""
    def __init__(self, prop):
        self.prop = prop

    def __repr__(self):
        return "C(%r)" % self.prop

    def __eq__(self, other):
        return isinstance(other, C) and self.prop == other.prop

    def __ne__(self, other):
        return not self.__eq__(other)


class f(object):
    """Helper factory for wait_until selftests. Creates a callable object that
    returns the specified values one by one each time it is called.

    Values are specified as space-separated characters. `.` means `None`,
    `F` means `False`, and `E` means raise a RuntimeError exception.
    """

    mapping = {".": None, "F": False, "C1": C(1), "C2": C(2), "C3": C(3),
               "E": RuntimeError("test exception")}

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
        if isinstance(v, Exception):
            raise v
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

    # predicate behaviour
    (f("a b b"), {"predicate": lambda x: x == "b"}, "b"),
    (f("F F F"), {"predicate": lambda x: x == "b"}, False),
    (f("C1 C2"), {"predicate": lambda x: x.prop == 2}, C(2)),
    (f("C1 C2"), {"predicate": lambda x: x.prop == 3}, None),

    # stable_secs behaviour
    (f("a b b"), {}, "a"),
    (f("a b b"), {"stable_secs": 1}, "b"),
    (f("a b c"), {"stable_secs": 1}, None),
    (f("C1 C2 C3"), {"stable_secs": 1,
                     "predicate": lambda x: 2 <= x.prop <= 3}, C(2)),

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
    (f("F F F"), {"stable_secs": 1}, False),
    (Zero, {"interval_secs": 1}, Zero()),
    (Zero, {"interval_secs": 1, "stable_secs": 1}, Zero()),
])
def test_wait_until(mock_time, f, kwargs, expected):
    assert wait_until(f, **kwargs) == expected


def test_that_wait_until_times_out(mock_time):
    assert not wait_until(Zero, interval_secs=1)
    assert time.time() == 1497000010


def test_that_wait_until_returns_first_stable_value(mock_time):

    def MR(match, x):
        time.sleep(1)  # advance the mock time by 1 second
        return stbt.MatchResult(
            time.time(), match, stbt.Region(x=x, y=0, width=10, height=2),
            first_pass_result=1,
            frame=numpy.random.randint(0, 255, (2, 2, 3)).astype(numpy.uint8),
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

    result = wait_until(match, predicate=lambda x: x and x.region,
                        stable_secs=2)
    assert result.match
    assert result.region.x == 4
    assert result.time == 1497000004


def test_that_wait_until_doesnt_compare_return_values(mock_time):
    class MR(object):
        def __init__(self, eq_allowed=False):
            time.sleep(1)  # advance the mock time by 1 second
            self.eq_allowed = eq_allowed

        def __eq__(self, other):
            if self.eq_allowed:
                return isinstance(other, MR)
            else:
                assert False, "Got unexpected call to MR.__eq__"

        def __ne__(self, other):
            return not self.__eq__(other)

    result = wait_until(MR)
    assert isinstance(result, MR)

    # But it does compare values if you specify `stable_secs`
    with pytest.raises(AssertionError):
        result = wait_until(MR, stable_secs=2)


def test_wait_until_ignored_exceptions(mock_time):
    with pytest.raises(RuntimeError):
        wait_until(f("E E F F T"))

    assert wait_until(f("E E F F T"), ignored_exceptions=RuntimeError) == "T"
    assert wait_until(f("F E T"), ignored_exceptions=RuntimeError) == "T"

    # Can specify a parent class of the exception:
    assert wait_until(f("E T"), ignored_exceptions=StandardError) == "T"
    # Can specify a tuple of exceptions:
    assert wait_until(f("E T"),
                      ignored_exceptions=(ValueError, RuntimeError)) == "T"

    def predicate(x):
        assert x.islower()
        return x

    # Also catches exceptions raised by the predicate function:
    assert wait_until(f("A b b"), predicate=predicate,
                      ignored_exceptions=AssertionError) == "b"
