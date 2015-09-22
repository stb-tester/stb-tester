# coding: utf-8
"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
Copyright 2013-2015 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

import _stbt.core
from _stbt.core import \
    as_precondition, \
    debug, \
    get_config, \
    ConfigurationError, \
    MatchParameters, \
    MatchResult, \
    MatchTimeout, \
    MotionResult, \
    MotionTimeout, \
    NoVideo, \
    OcrMode, \
    Position, \
    PreconditionError, \
    Region, \
    save_frame, \
    TextMatchResult, \
    UITestError, \
    UITestFailure, \
    wait_until

__all__ = [
    "as_precondition",
    "ConfigurationError",
    "debug",
    "detect_match",
    "detect_motion",
    "draw_text",
    "frames",
    "get_config",
    "get_frame",
    "is_screen_black",
    "match",
    "match_text",
    "MatchParameters",
    "MatchResult",
    "MatchTimeout",
    "MotionResult",
    "MotionTimeout",
    "NoVideo",
    "ocr",
    "OcrMode",
    "Position",
    "PreconditionError",
    "press",
    "press_until_match",
    "Region",
    "save_frame",
    "TextMatchResult",
    "UITestError",
    "UITestFailure",
    "wait_for_match",
    "wait_for_motion",
    "wait_until",
]

_dut = _stbt.core.DeviceUnderTest()

# Functions available to stbt scripts
# ===========================================================================


def press(key, interpress_delay_secs=None):
    """Send the specified key-press to the system under test.

    :param str key:
        The name of the key/button (as specified in your remote-control
        configuration file).

    :type interpress_delay_secs: int or float
    :param interpress_delay_secs:
        The minimum time to wait after a previous key-press, in order to
        accommodate the responsiveness of the device-under-test.

        This defaults to 0.3. You can override the global default value by
        setting ``interpress_delay_secs`` in the ``[press]`` section of
        stbt.conf.
    """
    return _dut.press(key, interpress_delay_secs)


def draw_text(text, duration_secs=3):
    """Write the specified text to the output video.

    :param str text: The text to write.

    :param duration_secs: The number of seconds to display the text.
    :type duration_secs: int or float
    """
    return _dut.draw_text(text, duration_secs)


def match(image, frame=None, match_parameters=None, region=Region.ALL):
    """
    Search for an image in a single video frame.

    :type image: string or numpy.ndarray
    :param image:
      The image to search for. It can be the filename of a png file on disk, or
      a numpy array containing the pixel data in 8-bit BGR format.

      8-bit BGR numpy arrays are the same format that OpenCV uses for images.
      This allows generating templates on the fly (possibly using OpenCV) or
      searching for images captured from the system-under-test earlier in the
      test script.

    :param numpy.ndarray frame:
      If this is specified it is used as the video frame to search in;
      otherwise a new frame is grabbed from the system-under-test. This is an
      image in OpenCV format (for example as returned by `frames` and
      `get_frame`).

    :param match_parameters:
      Customise the image matching algorithm. See `MatchParameters` for details.
    :type match_parameters: `MatchParameters`

    :param region:
      Only search within the specified region of the video frame.
    :type region: `Region`

    :returns:
      A `MatchResult`, which will evaluate to true if a match was found,
      false otherwise.
    """
    return _dut.match(image, frame, match_parameters, region)


def detect_match(image, timeout_secs=10, match_parameters=None):
    """Generator that yields a sequence of one `MatchResult` for each frame
    processed from the system-under-test's video stream.

    `image` is the image used as the template during matching.  See `stbt.match`
    for more information.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.
    """
    return _dut.detect_match(image, timeout_secs, match_parameters)


def detect_motion(timeout_secs=10, noise_threshold=None, mask=None):
    """Generator that yields a sequence of one `MotionResult` for each frame
    processed from the system-under-test's video stream.

    The `MotionResult` indicates whether any motion was detected -- that is,
    any difference between two consecutive frames.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. After this timeout the iterator will be exhausted.
        Thas is, a ``for`` loop like ``for m in detect_motion(timeout_secs=10)``
        will terminate after 10 seconds. If ``timeout_secs`` is ``None`` then
        the iterator will yield frames forever. Note that you can stop
        iterating (for example with ``break``) at any time.

    :param float noise_threshold:
        The amount of noise to ignore. This is only useful with noisy analogue
        video sources. Valid values range from 0 (all differences are
        considered noise; a value of 0 will never report motion) to 1.0 (any
        difference is considered motion).

        This defaults to 0.84. You can override the global default value by
        setting ``noise_threshold`` in the ``[motion]`` section of stbt.conf.

    :param str mask:
        The filename of a black & white image that specifies which part of the
        image to search for motion. White pixels select the area to search;
        black pixels select the area to ignore.
    """
    return _dut.detect_motion(timeout_secs, noise_threshold, mask)


def wait_for_match(image, timeout_secs=10, consecutive_matches=1,
                   match_parameters=None):
    """Search for an image in the system-under-test's video stream.

    :param image: The image to search for. See `match`.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. This function will raise `MatchTimeout` if no
        match is found within this time.

    :param int consecutive_matches:
        Forces this function to wait for several consecutive frames with a
        match found at the same x,y position. Increase ``consecutive_matches``
        to avoid false positives due to noise, or to wait for a moving
        selection to stop moving.

    :param match_parameters: See `match`.

    :returns: `MatchResult` when the image is found.
    :raises: `MatchTimeout` if no match is found after ``timeout_secs`` seconds.
    """
    return _dut.wait_for_match(
        image, timeout_secs, consecutive_matches, match_parameters)


def press_until_match(
        key,
        image,
        interval_secs=None,
        max_presses=None,
        match_parameters=None):
    """Call `press` as many times as necessary to find the specified image.

    :param key: See `press`.

    :param image: See `match`.

    :type interval_secs: int or float
    :param interval_secs:
        The number of seconds to wait for a match before pressing again.
        Defaults to 3.

        You can override the global default value by setting ``interval_secs``
        in the ``[press_until_match]`` section of stbt.conf.

    :param int max_presses:
        The number of times to try pressing the key and looking for the image
        before giving up and raising `MatchTimeout`. Defaults to 10.

        You can override the global default value by setting ``max_presses``
        in the ``[press_until_match]`` section of stbt.conf.

    :param match_parameters: See `match`.

    :returns: `MatchResult` when the image is found.
    :raises: `MatchTimeout` if no match is found after ``timeout_secs`` seconds.
    """
    return _dut.press_until_match(
        key, image, interval_secs, max_presses, match_parameters)


def wait_for_motion(
        timeout_secs=10, consecutive_frames=None,
        noise_threshold=None, mask=None):
    """Search for motion in the system-under-test's video stream.

    "Motion" is difference in pixel values between two consecutive frames.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. This function will raise `MotionTimeout` if no
        motion is detected within this time.

    :type consecutive_frames: int or str
    :param consecutive_frames:
        Considers the video stream to have motion if there were differences
        between the specified number of consecutive frames. This can be:

        * a positive integer value, or
        * a string in the form "x/y", where "x" is the number of frames with
          motion detected out of a sliding window of "y" frames.

        This defaults to "10/20". You can override the global default value by
        setting ``consecutive_frames`` in the ``[motion]`` section of stbt.conf.

    :param float noise_threshold: See `detect_motion`.

    :param str mask: See `detect_motion`.

    :returns: `MotionResult` when motion is detected.
    :raises: `MotionTimeout` if no motion is detected after ``timeout_secs``
        seconds.
    """
    return _dut.wait_for_motion(
        timeout_secs, consecutive_frames, noise_threshold, mask)


def ocr(frame=None, region=Region.ALL,
        mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD,
        lang="eng", tesseract_config=None, tesseract_user_words=None,
        tesseract_user_patterns=None):
    r"""Return the text present in the video frame as a Unicode string.

    Perform OCR (Optical Character Recognition) using the "Tesseract"
    open-source OCR engine.

    :param frame:
        The video frame to process. If not specified, take a frame from the
        system-under-test.

    :param region: Only search within the specified region of the video frame.
    :type region: `Region`

    :param mode: Tesseract's layout analysis mode.
    :type mode: `OcrMode`

    :param str lang:
        The three-letter
        `ISO-639-3 <http://www.loc.gov/standards/iso639-2/php/code_list.php>`_
        language code of the language you are attempting to read; for example
        "eng" for English or "deu" for German. More than one language can be
        specified by joining with '+'; for example "eng+deu" means that the
        text to be read may be in a mixture of English and German. Defaults to
        English.

    :param dict tesseract_config:
        Allows passing configuration down to the underlying OCR engine.
        See the `tesseract documentation
        <https://code.google.com/p/tesseract-ocr/wiki/ControlParams>`_
        for details.

    :type tesseract_user_words: list of unicode strings
    :param tesseract_user_words:
        List of words to be added to the tesseract dictionary. To replace the
        tesseract system dictionary altogether, also set
        ``tesseract_config={'load_system_dawg': False, 'load_freq_dawg':
        False}``.

    :type tesseract_user_patterns: list of unicode strings
    :param tesseract_user_patterns:
        List of patterns to add to the tesseract dictionary. The tesseract
        pattern language corresponds roughly to the following regular
        expressions::

            tesseract  regex
            =========  ===========
            \c         [a-zA-Z]
            \d         [0-9]
            \n         [a-zA-Z0-9]
            \p         [:punct:]
            \a         [a-z]
            \A         [A-Z]
            \*         *

    """
    return _dut.ocr(frame, region, mode, lang, tesseract_config,
                    tesseract_user_words, tesseract_user_patterns)


def match_text(text, frame=None, region=Region.ALL,
               mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD, lang="eng",
               tesseract_config=None):
    """Search for the specified text in a single video frame.

    This can be used as an alternative to `match`, searching for text instead
    of an image.

    :param unicode text: The text to search for.
    :param frame: See `ocr`.
    :param region: See `ocr`.
    :param mode: See `ocr`.
    :param lang: See `ocr`.
    :param tesseract_config: See `ocr`.

    :returns:
      A `TextMatchResult`, which will evaluate to True if the text was found,
      false otherwise.

    For example, to select a button in a vertical menu by name (in this case
    "TV Guide")::

        m = stbt.match_text("TV Guide")
        assert m.match
        while not stbt.match('selected-button.png').region.contains(m.region):
            stbt.press('KEY_DOWN')

    """
    return _dut.match_text(
        text, frame, region, mode, lang, tesseract_config)


def frames(timeout_secs=None):
    """Generator that yields video frames captured from the system-under-test.

    :type timeout_secs: int or float or None
    :param timeout_secs:
      A timeout in seconds. After this timeout the iterator will be exhausted.
      That is, a ``for`` loop like ``for f, t in frames(timeout_secs=10)`` will
      terminate after 10 seconds. If ``timeout_secs`` is ``None`` (the default)
      then the iterator will yield frames forever. Note that you can stop
      iterating (for example with ``break``) at any time.

    :returns:
      An ``(image, timestamp)`` tuple for each video frame, where ``image`` is
      a `numpy.ndarray` object (that is, an OpenCV image).
    """
    return _dut.frames(timeout_secs)


def get_frame():
    """:returns: The latest video frame in OpenCV format (`numpy.ndarray`)."""
    return _dut.get_frame()


def is_screen_black(frame=None, mask=None, threshold=None):
    """Check for the presence of a black screen in a video frame.

    :param numpy.ndarray frame:
      If this is specified it is used as the video frame to check; otherwise a
      new frame is grabbed from the system-under-test. This is an image in
      OpenCV format (for example as returned by `frames` and `get_frame`).

    :param str mask:
      The filename of a black & white image mask. It must have white pixels for
      parts of the frame to check and black pixels for any parts to ignore.

    :param int threshold:
      Even when a video frame appears to be black, the intensity of its pixels
      is not always 0. To differentiate almost-black from non-black pixels, a
      binary threshold is applied to the frame. The `threshold` value is in the
      range 0 (black) to 255 (white). The global default can be changed by
      setting `threshold` in the `[is_screen_black]` section of stbt.conf.
    """
    return _dut.is_screen_black(frame, mask, threshold)


def init_run(
        gst_source_pipeline, gst_sink_pipeline, control_uri, save_video=False,
        restart_source=False, transformation_pipeline='identity'):
    global _dut
    dut = _stbt.core.new_device_under_test_from_config(
        gst_source_pipeline, gst_sink_pipeline, control_uri, save_video,
        restart_source, transformation_pipeline)
    dut.__enter__()
    _dut = dut


def teardown_run():
    _dut.__exit__(None, None, None)
