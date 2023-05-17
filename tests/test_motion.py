import time
from contextlib import contextmanager

import numpy
import pytest

import stbt_core as stbt


def test_motionresult_repr():
    assert repr(stbt.MotionResult(
        time=1466002032.335607, motion=True,
        region=stbt.Region(x=321, y=32, right=334, bottom=42),
        frame=stbt.Frame(numpy.zeros((720, 1280, 3)),
                         time=1466002032.335607))) \
        == ("MotionResult("
            "time=1466002032.336, motion=True, "
            "region=Region(x=321, y=32, right=334, bottom=42), "
            "frame=<Frame(time=1466002032.336)>)")


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


def test_that_wait_for_motion_detects_a_wipe():
    stbt.wait_for_motion(consecutive_frames="10/30", frames=wipe())
    stbt.wait_for_motion(frames=gradient_wipe())


def test_detect_motion_region_and_mask():
    def dm(**kwargs):
        return next(stbt.detect_motion(frames=wipe(), **kwargs))

    r = stbt.Region(0, 0, right=640, bottom=1280)

    # Just check no exceptions
    dm()
    dm(mask="mask-out-left-half-720p.png")
    dm(mask=numpy.full((720, 1280), 255, dtype=numpy.uint8))
    dm(mask=r)
    dm(region=r)

    with pytest.raises(ValueError,
                       match="Cannot specify mask and region at the same time"):
        dm(region=r, mask=numpy.zeros((720, 1280), dtype=numpy.uint8))

    with pytest.raises(ValueError,
                       match=r"Mask\(<Image>\) doesn't overlap with the frame"):
        dm(mask=numpy.zeros((720, 1280), dtype=numpy.uint8))

    with pytest.raises(ValueError,
                       match=r"~Region.ALL doesn't overlap with the frame"):
        dm(mask=~stbt.Region.ALL)


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


def wipe():
    frame = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    for x in range(0, 720, 2):
        frame[x:x + 2, :, :] = 255
        yield stbt.Frame(frame.copy(), time=x / 30.)


def clamp(x, bottom, top):
    return min(top, max(bottom, x))


def gradient_wipe(min_=100, max_=200, swipe_height=40):
    """Use write_video(gradient_wipe()) to see what this looks like."""
    frame = min_ * numpy.ones(
        (720 + swipe_height * 4, 1280, 3), dtype=numpy.uint8)
    diff = max_ - min_

    # detect_motion ignores differences of under 25, so what's the fastest we
    # can wipe while making sure the inter-frame differences are always under
    # 25?:
    speed = 24 * swipe_height / diff

    print("pixel difference: %f" % (diff / swipe_height))
    print("max_speed: %f" % speed)

    edge = numpy.ones((swipe_height * 3, 1280, 3), dtype=numpy.uint8) * min_
    for n in range(swipe_height * 3):
        edge[n, :, :] = clamp(max_ - (n - swipe_height) * diff / swipe_height,
                              min_, max_)

    for x in range(0, frame.shape[0] - swipe_height * 3, int(speed)):
        frame[x:x + swipe_height * 3, :, :] = edge
        yield stbt.Frame(frame[swipe_height * 2:swipe_height * 2 + 720].copy(),
                         time=x / 30.)


def write_video(g):
    """This was useful during the development of wipe and gradient_wipe.
    Usage: write_video(gradient_wipe())"""
    import cv2

    vw = cv2.VideoWriter("test.avi", cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'),
                         30, (1280, 720))
    for frame in g:
        vw.write(frame)
    vw.release()


class MockTime():
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

    def at(self, offset, func):
        self._functions.append((self._time + offset, func))
        self._functions.sort()

    @contextmanager
    def assert_duration(self, seconds):
        start_time = self._time
        yield self
        assert self._time - start_time == seconds

    @contextmanager
    def patch(self):
        from unittest.mock import patch

        with patch("time.time", self.time), \
                patch("time.sleep", self.sleep):
            yield self
