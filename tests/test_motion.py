from contextlib import contextmanager

import numpy

import stbt


def test_motionresult_repr():
    assert repr(stbt.MotionResult(
        time=1466002032.335607, motion=True,
        region=stbt.Region(x=321, y=32, right=334, bottom=42),
        frame=numpy.zeros((720, 1280, 3)))) \
        == ("MotionResult("
            "time=1466002032.335607, motion=True, "
            "region=Region(x=321, y=32, right=334, bottom=42), "
            "frame=<1280x720x3>)")


def test_wait_for_motion_half_motion_str_2of4():
    with _fake_frames_at_half_motion() as dut:
        res = dut.wait_for_motion(consecutive_frames='2/4')
        print res
        assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_2of3():
    with _fake_frames_at_half_motion() as dut:
        res = dut.wait_for_motion(consecutive_frames='2/3')
        print res
        assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_4of10():
    with _fake_frames_at_half_motion() as dut:
        # Time is not affected by consecutive_frames parameter
        res = dut.wait_for_motion(consecutive_frames='4/10', timeout_secs=20)
        assert res.time == 1466084606.


def test_wait_for_motion_half_motion_str_3of4():
    with _fake_frames_at_half_motion() as dut:
        try:
            dut.wait_for_motion(consecutive_frames='3/4')
            assert False, "wait_for_motion succeeded unexpectedly"
        except stbt.MotionTimeout:
            pass


def test_wait_for_motion_half_motion_int():
    with _fake_frames_at_half_motion() as dut:
        try:
            dut.wait_for_motion(consecutive_frames=2)
            assert False, "wait_for_motion succeeded unexpectedly"
        except stbt.MotionTimeout:
            pass


@contextmanager
def _fake_frames_at_half_motion():
    from _stbt.core import DeviceUnderTest, NoSinkPipeline

    FRAMES = []
    a = numpy.zeros((2, 2, 3), dtype=numpy.uint8)
    b = numpy.ones((2, 2, 3), dtype=numpy.uint8) * 255

    # Motion:                 v     v     v     v     v     v     v     v     v
    data = [a, a, a, a, a, a, b, b, a, a, b, b, a, a, b, b, a, a, b, b, a, a, b]
    #       ^                 ^
    #       |                 L Motion starts here at timestamp 1466084606.
    #       L Video starts here at timestamp 1466084600

    FRAMES = [stbt.Frame(x, time=1466084600. + n) for n, x in enumerate(data)]

    class FakeDisplay(object):
        def get_frame(self, timeout_secs=10, since=0):  # pylint: disable=unused-argument
            for f in FRAMES:
                if f.time > since:
                    return f
            f = FRAMES[-1].copy()
            f.time = since + 1
            return f

    class FakeTime(object):
        def __init__(self, now):
            self._now = now

        def time(self):
            return self._now

        def sleep(self, duration):
            self._now += duration

    dut = DeviceUnderTest(display=FakeDisplay(), sink_pipeline=NoSinkPipeline(),
                          _time=FakeTime(FRAMES[0].time))
    yield dut
