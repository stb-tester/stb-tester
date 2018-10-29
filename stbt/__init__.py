# coding: utf-8
"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
Copyright 2013-2018 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

import sys
from contextlib import contextmanager

import _stbt.core
from _stbt.core import \
    as_precondition, \
    load_image, \
    NoVideo, \
    PreconditionError, \
    save_frame, \
    wait_until
from _stbt.config import (
    ConfigurationError,
    get_config)
from _stbt.frameobject import (
    FrameObject)
from _stbt.imgutils import (
    crop,
    Frame)
from _stbt.logging import (
    debug)
from _stbt.match import (
    detect_match,
    match,
    match_all,
    MatchParameters,
    MatchResult,
    MatchTimeout,
    Position,
    wait_for_match)
from _stbt.motion import (
    detect_motion,
    MotionResult,
    MotionTimeout,
    wait_for_motion)
from _stbt.navigation import (
    navigate_fixed_layout)
from _stbt.ocr import \
    match_text, \
    ocr, \
    OcrMode, \
    TextMatchResult
from _stbt.transition import \
    press_and_wait, \
    TransitionStatus, \
    wait_for_transition_to_end
from _stbt.types import (
    Region,
    UITestError,
    UITestFailure)

__all__ = [
    "as_precondition",
    "ConfigurationError",
    "crop",
    "debug",
    "detect_match",
    "detect_motion",
    "draw_text",
    "Frame",
    "FrameObject",
    "frames",
    "get_config",
    "get_frame",
    "is_screen_black",
    "load_image",
    "match",
    "match_all",
    "match_text",
    "MatchParameters",
    "MatchResult",
    "MatchTimeout",
    "MotionResult",
    "MotionTimeout",
    "navigate_fixed_layout",
    "NoVideo",
    "ocr",
    "OcrMode",
    "Position",
    "PreconditionError",
    "press",
    "press_and_wait",
    "press_until_match",
    "Region",
    "save_frame",
    "TextMatchResult",
    "TransitionStatus",
    "UITestError",
    "UITestFailure",
    "wait_for_match",
    "wait_for_motion",
    "wait_for_transition_to_end",
    "wait_until",
]

_dut = _stbt.core.DeviceUnderTest()

# Functions available to stbt scripts
# ===========================================================================


def press(key, interpress_delay_secs=None, hold_secs=None):
    """Send the specified key-press to the device under test.

    :param str key:
        The name of the key/button.

        If you are using infrared control, this is a key name from your
        lircd.conf configuration file.

        If you are using HDMI CEC control, see the available key names
        `here <https://github.com/stb-tester/stb-tester/blob/v28/_stbt/control_gpl.py#L18-L117>`__.
        Note that some devices might not understand all of the CEC commands in
        that list.

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

    Added in v29: The ``hold_secs`` parameter.
    """
    return _dut.press(key, interpress_delay_secs, hold_secs)


def pressing(key, interpress_delay_secs=None):
    """Context manager that will press and hold the specified key for the
    duration of the ``with`` code block.

    For example, this will hold KEY_RIGHT until ``wait_for_match`` finds a
    match or times out::

        with stbt.pressing("KEY_RIGHT"):
            stbt.wait_for_match("last-page.png")

    The same limitations apply as `stbt.press`'s ``hold_secs`` parameter.

    This function was added in v29.
    """
    return _dut.pressing(key, interpress_delay_secs)


def draw_text(text, duration_secs=3):
    """Write the specified text to the output video.

    :param str text: The text to write.

    :param duration_secs: The number of seconds to display the text.
    :type duration_secs: int or float
    """
    return _dut.draw_text(text, duration_secs)


def press_until_match(
        key,
        image,
        interval_secs=None,
        max_presses=None,
        match_parameters=None,
        region=Region.ALL):
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

    Added in v28: The ``region`` parameter.
    """
    return _dut.press_until_match(
        key, image, interval_secs, max_presses, match_parameters, region)


def frames(timeout_secs=None):
    """Generator that yields video frames captured from the device-under-test.

    :type timeout_secs: int or float or None
    :param timeout_secs:
      A timeout in seconds. After this timeout the iterator will be exhausted.
      That is, a ``for`` loop like ``for f in frames(timeout_secs=10)`` will
      terminate after 10 seconds. If ``timeout_secs`` is ``None`` (the default)
      then the iterator will yield frames forever. Note that you can stop
      iterating (for example with ``break``) at any time.

    :rtype: Iterator[stbt.Frame]
    :returns:
      An iterator of frames in OpenCV format (`stbt.Frame`).

    Changed in v29: Returns ``Iterator[stbt.Frame]`` instead of
    ``Iterator[(stbt.Frame, int)]``. Use the Frame's ``time`` attribute
    instead.
    """
    return _dut.frames(timeout_secs)


def get_frame():
    """Grabs a video frame captured from the device-under-test.

    :returns: The latest video frame in OpenCV format (a `stbt.Frame`).
    """
    return _dut.get_frame()


def is_screen_black(frame=None, mask=None, threshold=None, region=Region.ALL):
    """Check for the presence of a black screen in a video frame.

    :type frame: `stbt.Frame` or `numpy.ndarray`
    :param frame:
      If this is specified it is used as the video frame to check; otherwise a
      new frame is grabbed from the device-under-test. This is an image in
      OpenCV format (for example as returned by `frames` and `get_frame`).

    :type mask: str or `numpy.ndarray`
    :param mask:
        A black & white image that specifies which part of the image to
        analyse. White pixels select the area to analyse; black pixels select
        the area to ignore. The mask must be the same size as the video frame.

        This can be a string (a filename that will be resolved as per
        `load_image`) or a single-channel image in OpenCV format.

    :param int threshold:
      Even when a video frame appears to be black, the intensity of its pixels
      is not always 0. To differentiate almost-black from non-black pixels, a
      binary threshold is applied to the frame. The ``threshold`` value is in
      the range 0 (black) to 255 (white). The global default can be changed by
      setting ``threshold`` in the ``[is_screen_black]`` section of
      :ref:`.stbt.conf`.

    :type region: `Region`
    :param region:
        Only analyze the specified region of the video frame.

        If you specify both ``region`` and ``mask``, the mask must be the same
        size as the region.

    :returns:
        An object that will evaluate to true if the frame was black, or false
        if not black. The object has the following attributes:

        * **black** (*bool*) – True if the frame was black.
        * **frame** (`stbt.Frame`) – The video frame that was analysed.

    | Added in v28: The ``region`` parameter.
    | Added in v29: Return an object with a frame attribute, instead of bool.
    """
    return _dut.is_screen_black(frame, mask, threshold, region)


@contextmanager
def _set_dut_singleton(dut):
    global _dut
    old_dut = dut
    try:
        _dut = dut
        yield dut
    finally:
        _dut = old_dut
