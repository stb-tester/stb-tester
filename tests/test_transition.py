import cv2
import numpy
import pytest
from numpy import isclose

import stbt_core as stbt
from _stbt.logging import scoped_debug_level
from _stbt.transition import Transition
from _stbt.types import Keypress


class FakeDeviceUnderTest():
    def __init__(self, frames=None, ignores=0):
        self.state = "black"
        self._frames = iter(frames) if frames else None
        self._t = 0
        self._ignores = ignores

    def press(self, key):
        print(f"FakeDeviceUnderTest.press({key})")
        frame_before = next(self.frames())
        if self._ignores == 0:
            self.state = key
        else:
            print(f"(FakeDeviceUnderTest ignored key {key})")
            self._ignores -= 1
        return Keypress(key, self._t, self._t, frame_before)

    def frames(self):
        if self._frames is not None:
            # Ignore self.state, send the specified frames instead.
            for state in self._frames:  # pylint:disable=not-an-iterable
                self._t += 0.04  # 25fps
                array = F(state, self._t)
                yield stbt.Frame(array, time=self._t)

        else:
            while True:
                self._t += 0.04  # 25fps
                array = F(self.state, self._t)
                if self.state == "fade-to-black":
                    self.state = "black"
                elif self.state == "fade-to-white":
                    self.state = "white"
                yield stbt.Frame(array, time=self._t)


def F(state, t):
    if state == "black":
        array = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    elif state == "white":
        array = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255
    elif state in ["fade-to-black", "fade-to-white"]:
        array = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 127
    elif state == "ball":
        # black background, white ball that moves by 1 pixel every 10ms
        # in the left half of the frame.
        array = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
        cv2.circle(array, (int(t * 100) % 625, 360), 15, (255, 255, 255), -1)
    return array


@pytest.fixture(scope="function", params=[stbt.BGRDiff(), stbt.GrayscaleDiff()])
def diff_algorithm(request):
    previous = stbt.press_and_wait.differ
    try:
        stbt.press_and_wait.differ = request.param
        yield stbt.press_and_wait.differ
    finally:
        stbt.press_and_wait.differ = previous


# pylint:disable=redefined-outer-name,unused-argument

@pytest.mark.parametrize("min_size", [None, (20, 20)])
def test_press_and_wait(diff_algorithm, min_size):
    _stbt = FakeDeviceUnderTest()

    transition = stbt.press_and_wait("white", min_size=min_size,
                                     stable_secs=0.1, _dut=_stbt)
    print(transition)
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE
    assert transition.press_time < transition.animation_start_time
    assert transition.animation_start_time == transition.end_time
    assert transition.duration == 0.04  # excludes stable period
    assert transition.frame.min() == 255

    transition = stbt.press_and_wait("fade-to-black", min_size=min_size,
                                     stable_secs=0.1, _dut=_stbt)
    print(transition)
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE
    assert transition.animation_start_time < transition.end_time
    assert transition.frame.max() == 0


@pytest.mark.parametrize("min_size", [None, (20, 20)])
def test_press_and_wait_start_timeout(diff_algorithm, min_size):
    transition = stbt.press_and_wait("black", min_size=min_size,
                                     timeout_secs=0.2, stable_secs=0.1,
                                     _dut=FakeDeviceUnderTest())
    print(transition)
    assert not transition
    assert transition.status == stbt.TransitionStatus.START_TIMEOUT


@pytest.mark.parametrize("min_size", [None, (20, 20)])
def test_press_and_wait_stable_timeout(diff_algorithm, min_size):
    transition = stbt.press_and_wait("ball", min_size=min_size,
                                     timeout_secs=0.2, stable_secs=0.1,
                                     _dut=FakeDeviceUnderTest())
    print(transition)
    assert not transition
    assert transition.status == stbt.TransitionStatus.STABLE_TIMEOUT

    transition = stbt.press_and_wait("ball", stable_secs=0,
                                     _dut=FakeDeviceUnderTest())
    print(transition)
    assert transition
    assert transition.status == stbt.TransitionStatus.COMPLETE


@pytest.mark.parametrize("mask,min_size,expected", [
    (stbt.Region.ALL, None, stbt.TransitionStatus.STABLE_TIMEOUT),
    ("mask-out-left-half-720p.png", None, stbt.TransitionStatus.START_TIMEOUT),
    (numpy.full((720, 1280), 255, dtype=numpy.uint8), None,
     stbt.TransitionStatus.STABLE_TIMEOUT),
    (stbt.Region(x=640, y=0, right=1280, bottom=720), None,
     stbt.TransitionStatus.START_TIMEOUT),
    (stbt.Region(x=0, y=0, right=1280, bottom=360), None,
     stbt.TransitionStatus.STABLE_TIMEOUT),
    (stbt.Region.ALL, (0, 32), stbt.TransitionStatus.START_TIMEOUT),
    (stbt.Region.ALL, (0, 10), stbt.TransitionStatus.STABLE_TIMEOUT),
    (~stbt.Region(x=10, y=340, right=640, bottom=380), None,
     stbt.TransitionStatus.STABLE_TIMEOUT),
])
def test_press_and_wait_with_mask_or_region(mask, min_size, expected,
                                            diff_algorithm):
    transition = stbt.press_and_wait(
        "ball", mask=mask, min_size=min_size, timeout_secs=0.2, stable_secs=0.1,
        _dut=FakeDeviceUnderTest())
    print(transition)
    assert transition.status == expected


def test_press_and_wait_region_parameter():
    # region is a synonym of mask, for backwards compatibility
    transition = stbt.press_and_wait(
        "ball", region=stbt.Region(x=640, y=0, right=1280, bottom=720),
        timeout_secs=0.2, stable_secs=0.1, _dut=FakeDeviceUnderTest())
    print(transition)
    assert transition.status == stbt.TransitionStatus.START_TIMEOUT

    with pytest.raises(ValueError,
                       match="Cannot specify mask and region at the same time"):
        stbt.press_and_wait(
            "ball",
            region=stbt.Region(x=640, y=0, right=1280, bottom=720),
            mask=stbt.Region(x=640, y=0, right=1280, bottom=720),
            timeout_secs=0.2, stable_secs=0.1, _dut=FakeDeviceUnderTest())


def test_press_and_wait_retries():
    with scoped_debug_level(1):

        transition = stbt.press_and_wait("white",
                                         timeout_secs=0.2, stable_secs=0.1,
                                         _dut=FakeDeviceUnderTest(ignores=2))
        print(transition)
        assert transition.status == stbt.TransitionStatus.START_TIMEOUT

        transition = stbt.press_and_wait("white", retries=1,
                                         timeout_secs=0.2, stable_secs=0.1,
                                         _dut=FakeDeviceUnderTest(ignores=2))
        print(transition)
        assert transition.status == stbt.TransitionStatus.START_TIMEOUT

        transition = stbt.press_and_wait("white", retries=2,
                                         timeout_secs=0.2, stable_secs=0.1,
                                         _dut=FakeDeviceUnderTest(ignores=2))
        print(transition)
        assert transition.status == stbt.TransitionStatus.COMPLETE


def test_wait_for_transition_to_end(diff_algorithm):
    _stbt = FakeDeviceUnderTest()

    transition = stbt.wait_for_transition_to_end(
        timeout_secs=0.2, stable_secs=0.1, frames=_stbt.frames())

    _stbt.press("ball")
    transition = stbt.wait_for_transition_to_end(
        timeout_secs=0.2, stable_secs=0.1, frames=_stbt.frames())
    print(transition)
    assert not transition
    assert transition.status == stbt.TransitionStatus.STABLE_TIMEOUT


def test_press_and_wait_timestamps(diff_algorithm):
    _stbt = FakeDeviceUnderTest(
        ["black"] * 10 + ["fade-to-white"] * 2 + ["white"] * 100)

    transition = stbt.press_and_wait("fade-to-white", _dut=_stbt)
    print(transition)
    assert transition
    assert isclose(transition.animation_start_time,
                   transition.press_time + 0.40)
    assert isclose(transition.duration, 0.48)
    assert isclose(transition.end_time, transition.animation_start_time + 0.08)
    assert isclose(transition.animation_duration, 0.08)


@pytest.mark.parametrize("status,          started,complete,stable", [
    # pylint:disable=bad-whitespace
    (stbt.TransitionStatus.START_TIMEOUT,  False,  False,   True),
    (stbt.TransitionStatus.STABLE_TIMEOUT, True,   False,   False),
    (stbt.TransitionStatus.COMPLETE,       True,   True,    True),
])
def test_transitionresult_properties(status, started, complete, stable):
    t = Transition(key="KEY_OK", frame=None, status=status,
                   press_time=0, animation_start_time=0, end_time=0)
    assert t.started == started
    assert t.complete == complete
    assert t.stable == stable
