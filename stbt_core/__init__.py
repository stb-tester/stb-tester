"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
Copyright 2013-2018 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import annotations

import typing
from contextlib import contextmanager
from typing import ContextManager, Iterator, Optional

from _stbt import android
from _stbt.black import (
    is_screen_black)
from _stbt.config import (
    ConfigurationError,
    get_config)
from _stbt.diff import (
    BGRDiff,
    Differ,
    GrayscaleDiff,
    MotionResult)
from _stbt.frameobject import (
    for_object_repository,
    FrameObject)
from _stbt.grid import (
    Grid)
from _stbt.imgutils import (
    Color,
    crop,
    find_file,
    Frame,
    Image,
    load_image,
    save_frame)
from _stbt.keyboard import (
    Keyboard)
from _stbt.logging import (
    debug)
from _stbt.mask import (
    load_mask,
    Mask,
    MaskTypes)
from _stbt.match import (
    ConfirmMethod,
    match,
    match_all,
    MatchMethod,
    MatchParameters,
    MatchResult,
    MatchTimeout,
    wait_for_match)
from _stbt.motion import (
    detect_motion,
    MotionTimeout,
    wait_for_motion)
from _stbt.multipress import (
    MultiPress)
from _stbt.ocr import (
    apply_ocr_corrections,
    match_text,
    ocr,
    ocr_eq,
    OcrEngine,
    OcrMode,
    set_global_ocr_corrections,
    TextMatchResult)
from _stbt.precondition import (
    as_precondition,
    PreconditionError)
from _stbt.transition import (
    press_and_wait,
    Transition,
    TransitionStatus,
    wait_for_transition_to_end)
from _stbt.types import (
    Direction,
    Keypress,
    NoVideo,
    PDU,
    Position,
    Region,
    Size,
    UITestError,
    UITestFailure)
from _stbt.wait import (
    wait_until)

__all__ = [
    "android",
    "apply_ocr_corrections",
    "as_precondition",
    "BGRDiff",
    "Color",
    "ConfigurationError",
    "ConfirmMethod",
    "crop",
    "debug",
    "detect_motion",
    "Differ",
    "Direction",
    "draw_text",
    "find_file",
    "for_object_repository",
    "Frame",
    "FrameObject",
    "frames",
    "get_config",
    "get_frame",
    "GrayscaleDiff",
    "Grid",
    "Image",
    "is_screen_black",
    "Keyboard",
    "Keypress",
    "last_keypress",
    "load_image",
    "load_mask",
    "Mask",
    "MaskTypes",
    "match",
    "match_all",
    "match_text",
    "MatchMethod",
    "MatchParameters",
    "MatchResult",
    "MatchTimeout",
    "MotionResult",
    "MotionTimeout",
    "MultiPress",
    "NoVideo",
    "ocr",
    "ocr_eq",
    "OcrEngine",
    "OcrMode",
    "PDU",
    "Position",
    "PreconditionError",
    "press",
    "press_and_wait",
    "press_until_match",
    "pressing",
    "Region",
    "save_frame",
    "set_global_ocr_corrections",
    "Size",
    "TextMatchResult",
    "Transition",
    "TransitionStatus",
    "UITestError",
    "UITestFailure",
    "wait_for_match",
    "wait_for_motion",
    "wait_for_transition_to_end",
    "wait_until",
]


from _stbt.imgutils import ImageT
from _stbt.types import KeyT, RegionT
if typing.TYPE_CHECKING:
    import _stbt.core


TEST_PACK_ROOT: "str|None" = None


# Functions available to stbt scripts
# ===========================================================================


def last_keypress() -> "Keypress|None":
    """Returns information about the last key-press sent to the device under
    test.

    See the return type of `stbt.press`.
    """
    return _dut.last_keypress()


def press(
    key: KeyT, interpress_delay_secs: Optional[float] = None,
    hold_secs: Optional[float] = None
) -> Keypress:
    """Send the specified key-press to the device under test.

    :param str key:
        The name of the key/button.

        If you are using infrared control, this is a key name from your
        lircd.conf configuration file.

        If you are using HDMI CEC control, see the available key names
        `here <https://stb-tester.com/kb/cec-names>`__. Note that some devices
        might not understand every CEC command in that list.

    :type interpress_delay_secs: int or float
    :param interpress_delay_secs:
        The minimum time to wait after a previous key-press, in order to
        accommodate the responsiveness of the device-under-test.

        This defaults to 0.3. You can override the global default value by
        setting ``interpress_delay_secs`` in the ``[press]`` section of
        :ref:`.stbt.conf`.

    :type hold_secs: int or float
    :param hold_secs:
        Hold the key down for the specified duration (in seconds). Currently
        this is implemented for the infrared, HDMI CEC, and Roku controls.
        There is a maximum limit of 60 seconds.

    :returns:
        A `stbt.Keypress` object with information about the keypress that was
        sent.

    * Changed in v33: The ``key`` argument can be an Enum (we'll use the Enum's
      value, which must be a string).
    """
    return _dut.press(key, interpress_delay_secs, hold_secs)


def pressing(
    key: KeyT, interpress_delay_secs: Optional[float] = None
) -> ContextManager[Keypress]:
    """Context manager that will press and hold the specified key for the
    duration of the ``with`` code block.

    For example, this will hold KEY_RIGHT until ``wait_for_match`` finds a
    match or times out::

        with stbt.pressing("KEY_RIGHT"):
            stbt.wait_for_match("last-page.png")

    The same limitations apply as `stbt.press`'s ``hold_secs`` parameter.
    """
    return _dut.pressing(key, interpress_delay_secs)


def draw_text(text: str, duration_secs: float = 3) -> None:
    """Write the specified text to the output video.

    :param str text: The text to write.

    :param duration_secs: The number of seconds to display the text.
    :type duration_secs: int or float
    """
    debug(text)
    return _dut.draw_text(text, duration_secs)


def press_until_match(
    key: KeyT,
    image: ImageT,
    interval_secs: Optional[float] = None,
    max_presses: Optional[int] = None,
    match_parameters: Optional[MatchParameters] = None,
    region: RegionT = Region.ALL,
) -> MatchResult:
    """Call `press` as many times as necessary to find the specified image.

    :param key: See `press`.

    :param image: See `match`.

    :type interval_secs: int or float
    :param interval_secs:
        The number of seconds to wait for a match before pressing again.
        Defaults to 3.

        You can override the global default value by setting ``interval_secs``
        in the ``[press_until_match]`` section of :ref:`.stbt.conf`.

    :param int max_presses:
        The number of times to try pressing the key and looking for the image
        before giving up and raising `MatchTimeout`. Defaults to 10.

        You can override the global default value by setting ``max_presses``
        in the ``[press_until_match]`` section of :ref:`.stbt.conf`.

    :param match_parameters: See `match`.
    :param region: See `match`.

    :returns: `MatchResult` when the image is found.
    :raises: `MatchTimeout` if no match is found after ``timeout_secs`` seconds.
    """
    return _dut.press_until_match(
        key, image, interval_secs, max_presses, match_parameters, region)


def frames(timeout_secs: Optional[float] = None) -> Iterator[Frame]:
    """Generator that yields video frames captured from the device-under-test.

    For example::

        for frame in stbt.frames():
            # Do something with each frame here.
            # Remember to add a termination condition to `break` or `return`
            # from the loop, or specify `timeout_secs` — otherwise you'll have
            # an infinite loop!
            ...

    See also `stbt.get_frame`.

    :type timeout_secs: int or float or None
    :param timeout_secs:
      A timeout in seconds. After this timeout the iterator will be exhausted.
      That is, a ``for`` loop like ``for f in stbt.frames(timeout_secs=10)``
      will terminate after 10 seconds. If ``timeout_secs`` is ``None`` (the
      default) then the iterator will yield frames forever but you can stop
      iterating (for example with ``break``) at any time.

    :rtype: Iterator[stbt.Frame]
    :returns:
      An iterator of frames in OpenCV format (`stbt.Frame`).
    """
    return _dut.frames(timeout_secs)


def get_frame() -> Frame:
    """Grabs a video frame from the device-under-test.

    :rtype: stbt.Frame
    :returns: The most recent video frame in OpenCV format.

    Most Stb-tester APIs (`stbt.match`, `stbt.FrameObject` constructors, etc.)
    will call ``get_frame`` if a frame isn't specified explicitly.

    If you call ``get_frame`` twice very quickly (faster than the video-capture
    framerate) you might get the same frame twice. To block until the next
    frame is available, use `stbt.frames`.

    To save a frame to disk pass it to :ocv:pyfunc:`cv2.imwrite`. Note that any
    file you write to the current working directory will appear as an artifact
    in the test-run results.
    """
    return _dut.get_frame()


# Internal
# ===========================================================================

class UnconfiguredDeviceUnderTest():
    def last_keypress(self):
        return None

    def press(self, *args, **kwargs):
        raise RuntimeError(
            "stbt.press isn't configured to run on your hardware")

    def pressing(self, *args, **kwargs):
        raise RuntimeError(
            "stbt.pressing isn't configured to run on your hardware")

    def draw_text(self, *args, **kwargs):
        # Unlike the others this has no external side-effects on the device
        # under test. `stbt.draw_text` already logs it before calling
        # `_dut.draw_text`. Really this shouldn't belong in the DUT at all.
        pass

    def press_until_match(self, *args, **kwargs):
        raise RuntimeError(
            "stbt.press_until_match isn't configured to run on your hardware")

    def frames(self, *args, **kwargs):
        raise RuntimeError(
            "stbt.frames isn't configured to run on your hardware")

    def get_frame(self, *args, **kwargs):
        raise RuntimeError(
            "stbt.get_frame isn't configured to run on your hardware")


_dut: "_stbt.core.DeviceUnderTest | UnconfiguredDeviceUnderTest" = (
    UnconfiguredDeviceUnderTest())


@contextmanager
def _set_dut_singleton(dut):
    global _dut
    old_dut = dut
    try:
        _dut = dut
        yield dut
    finally:
        _dut = old_dut
