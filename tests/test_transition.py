import time

import cv2
import numpy
import pytest
from numpy import isclose

import stbt


class FakeDeviceUnderTest(object):
    def __init__(self, frames=None):
        self.state = "black"
        self._frames = frames

    def press(self, key):
        self.state = key

    def frames(self):
        if self._frames is not None:
            # Ignore self.state, send the specified frames instead.
            t = time.time()
            for state in self._frames:
                array = F(state, t)
                yield stbt.Frame(array, time=t), int(t * 1e9)
                t += 0.04  # 25fps

        else:
            while True:
                t = time.time()
                array = F(self.state, t)
                if self.state == "fade-to-black":
                    self.state = "black"
                elif self.state == "fade-to-white":
                    self.state = "white"
                yield stbt.Frame(array, time=t), int(t * 1e9)


def F(state, t):
    if state == "black":
        array = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    elif state == "white":
        array = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255
    elif state in ["fade-to-black", "fade-to-white"]:
        array = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 127
    elif state == "ball":
        # black background, white ball that moves by 1 pixel ever 10ms
        # in the left half of the frame.
        array = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
        cv2.circle(array, (int(t * 100) % 625, 360), 15, (255, 255, 255))
    return array


def test_press_and_wait():
    _stbt = FakeDeviceUnderTest()

    transition = stbt.press_and_wait("white", stable_secs=0.1, _dut=_stbt)
    print transition
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE
    assert transition.press_time < transition.animation_start_time
    assert transition.animation_start_time == transition.end_time
    assert transition.duration < 0.01  # excludes stable period
    assert transition.frame.min() == 255

    transition = stbt.press_and_wait("fade-to-black", stable_secs=0.1,
                                     _dut=_stbt)
    print transition
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE
    assert transition.animation_start_time < transition.end_time
    assert transition.frame.max() == 0


def test_press_and_wait_start_timeout():
    transition = stbt.press_and_wait("black", timeout_secs=0.2, stable_secs=0.1,
                                     _dut=FakeDeviceUnderTest())
    print transition
    assert not transition
    assert transition.status == stbt.TransitionStatus.START_TIMEOUT


def test_press_and_wait_stable_timeout():
    transition = stbt.press_and_wait("ball", timeout_secs=0.2, stable_secs=0.1,
                                     _dut=FakeDeviceUnderTest())
    print transition
    assert not transition
    assert transition.status == stbt.TransitionStatus.STABLE_TIMEOUT

    transition = stbt.press_and_wait("ball", stable_secs=0,
                                     _dut=FakeDeviceUnderTest())
    print transition
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE


@pytest.mark.parametrize("mask,region,expected", [
    (None, stbt.Region.ALL, stbt.TransitionStatus.STABLE_TIMEOUT),
    ("mask-out-left-half-720p.png", stbt.Region.ALL,
     stbt.TransitionStatus.START_TIMEOUT),
    (None, stbt.Region(x=640, y=0, right=1280, bottom=720),
     stbt.TransitionStatus.START_TIMEOUT),
    (None, stbt.Region(x=0, y=0, right=1280, bottom=360),
     stbt.TransitionStatus.STABLE_TIMEOUT),
])
def test_press_and_wait_with_mask_or_region(mask, region, expected):
    transition = stbt.press_and_wait(
        "ball", mask=mask, region=region, timeout_secs=0.2, stable_secs=0.1,
        _dut=FakeDeviceUnderTest())
    print transition
    assert transition.status == expected


def test_wait_for_transition_to_end():
    _stbt = FakeDeviceUnderTest()

    transition = stbt.wait_for_transition_to_end(
        timeout_secs=0.2, stable_secs=0.1, _dut=_stbt)

    _stbt.press("ball")
    transition = stbt.wait_for_transition_to_end(
        timeout_secs=0.2, stable_secs=0.1, _dut=_stbt)
    print transition
    assert not transition
    assert transition.status == stbt.TransitionStatus.STABLE_TIMEOUT


def test_press_and_wait_timestamps():
    _stbt = FakeDeviceUnderTest(
        ["black"] * 10 + ["fade-to-white"] * 2 + ["white"] * 100)

    transition = stbt.press_and_wait("fade-to-white", _dut=_stbt)
    print transition
    assert transition
    assert isclose(transition.animation_start_time,
                   transition.press_time + 0.40,
                   rtol=0, atol=0.01)
    assert isclose(transition.duration, 0.48, rtol=0, atol=0.01)
    assert isclose(transition.end_time, transition.animation_start_time + 0.08)
    assert isclose(transition.animation_duration, 0.08)
