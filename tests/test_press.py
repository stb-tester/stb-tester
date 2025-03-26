from unittest.mock import Mock

import pytest

from _stbt.config import _config_init
from _stbt.control import RemoteControl
from _stbt.core import DeviceUnderTest, NoSinkPipeline


def test_that_pressing_context_manager_raises_keyup_exceptions():
    dut = DeviceUnderTest(control=FakeControl(raises_on_keyup=True),
                          display=_FakeDisplay(),
                          sink_pipeline=NoSinkPipeline())
    with pytest.raises(RuntimeError) as excinfo:
        with dut.pressing("KEY_MENU"):
            pass
    assert "keyup KEY_MENU failed" in str(excinfo.value)


def test_that_pressing_context_manager_suppresses_keyup_exceptions():
    # ...if doing so would hide an exception raised by the test script.
    control = FakeControl(raises_on_keyup=True)
    dut = DeviceUnderTest(control=control, display=_FakeDisplay(),
                          sink_pipeline=NoSinkPipeline())
    with pytest.raises(AssertionError):
        with dut.pressing("KEY_MENU"):
            assert False
    assert control.keyup_called == 1


def test_keymap_section():
    config = _config_init()
    try:
        config.add_section("control")
        config.set("control", "keymap_section", "my_keymap")
        config.add_section("my_keymap")
        config.set("my_keymap", "KEY_FLOOBLE", "KEY_UP")

        control = Mock(spec=RemoteControl)
        dut = DeviceUnderTest(control=control, display=_FakeDisplay(),
                              sink_pipeline=NoSinkPipeline())
        dut.press("KEY_OK")
        assert control.press.call_args[0] == ("KEY_OK",)
        keypress = dut.press("KEY_FLOOBLE")
        assert control.press.call_args[0] == ("KEY_UP",)
        assert keypress.key == "KEY_FLOOBLE"
        with dut.pressing("KEY_OK"):
            assert control.keydown.call_args[0] == ("KEY_OK",)
        assert control.keyup.call_args[0] == ("KEY_OK",)
        with dut.pressing("KEY_FLOOBLE") as keypress:
            assert control.keydown.call_args[0] == ("KEY_UP",)
        assert control.keyup.call_args[0] == ("KEY_UP",)
        assert keypress.key == "KEY_FLOOBLE"
    finally:
        _config_init(force=True)


class FakeControl():
    def __init__(self, raises_on_keydown=False, raises_on_keyup=False):
        self.raises_on_keydown = raises_on_keydown
        self.raises_on_keyup = raises_on_keyup
        self.keydown_called = 0
        self.keyup_called = 0

    def keydown(self, key):
        print("keydown %s" % key)
        self.keydown_called += 1
        if self.raises_on_keydown:
            raise RuntimeError("keydown %s failed" % key)

    def keyup(self, key):
        print("keyup %s" % key)
        self.keyup_called += 1
        if self.raises_on_keyup:
            raise RuntimeError("keyup %s failed" % key)


class _FakeDisplay():
    def get_frame(self):
        return None
