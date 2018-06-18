# coding: utf-8
"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
Copyright 2013-2015 stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

import sys
from contextlib import contextmanager

import _stbt.core
from _stbt.core import \
    as_precondition, \
    ConfigurationError, \
    crop, \
    debug, \
    Frame, \
    get_config, \
    load_image, \
    NoVideo, \
    PreconditionError, \
    Region, \
    save_frame, \
    UITestError, \
    UITestFailure, \
    wait_until
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
from _stbt.ocr import \
    match_text, \
    ocr, \
    OcrMode, \
    TextMatchResult
from _stbt.transition import \
    press_and_wait, \
    TransitionStatus, \
    wait_for_transition_to_end

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


class FrameObject(_stbt.core.FrameObject):
    # pylint: disable=line-too-long,abstract-method
    r'''Base class for user-defined Frame Objects.

    The Frame Object pattern is used to simplify testcase development and
    maintenance. Frame Objects are a layer of abstraction between your
    testcases and the stbt image processing APIs. They are easy to write and
    cheap to maintain.

    A Frame Object extracts information from a frame of video, typically by
    calling `stbt.ocr` or `stbt.match`. All of your testcases use these objects
    rather than using `ocr` or `match` directly. A Frame Object translates from
    the vocabulary of low-level image processing functions and regions (like
    ``stbt.ocr(region=stbt.Region(213, 23, 200, 36))``) to the vocabulary of
    high-level features and user-facing concepts (like ``programme_title``).

    ``FrameObject`` is a base class that makes it easier to create well-behaved
    Frame Objects. Your own Frame Object classes should:

    1. Derive from ``FrameObject``.
    2. Define an ``is_visible`` property that returns True or False.
    3. Define any other properties for information that you want to extract
       from the frame.
    4. Take care to pass ``self._frame`` into any image processing function you
       call.

    A Frame Object instance is considered "truthy" if it is visible. Any other
    properties (apart from ``is_visible``) will return ``None`` if the object
    isn't visible.

    Frame Objects are immutable, because they represent information about a
    specific frame of video. If you define any methods that change the state of
    the device-under-test, they should return a new Frame Object instead of
    modifying ``self``.

    Each property will be cached the first time is is referenced. This allows
    writing test cases in a natural way while expensive operations like ``ocr``
    will only be done once per frame.

    The ``FrameObject`` base class defines the following methods:

    * ``__init__`` -- The default constructor takes an optional frame; if the
      frame is not provided, it will grab a frame from the device-under-test.
    * ``__nonzero__`` -- Delegates to ``is_visible``. The object will only be
      considered True if it is visible.
    * ``__repr__`` -- The object's string representation includes all the
      user-defined public properties.
    * ``__hash__`` and ``__cmp__`` -- Two instances of the same ``FrameObject``
      type are considered equal if the values of all the public properties
      match, even if the underlying frame is different.

    For more background information on Frame Objects see
    `Improve black-box testing agility: meet the Frame Object pattern
    <https://stb-tester.com/blog/2015/09/08/meet-the-frame-object-pattern>`__.

    **Example**

    We'll create a Frame Object class for the dialog box we see in this image
    that we've captured from our (hypothetical) set-top box:

    .. figure:: images/frame-object-with-dialog.png
       :alt: screenshot of dialog box

    Here's our Frame Object class:

    >>> class Dialog(FrameObject):
    ...     @property
    ...     def is_visible(self):
    ...         return bool(self._info)
    ...
    ...     @property
    ...     def title(self):
    ...         return ocr(region=Region(396, 249, 500, 50), frame=self._frame)
    ...
    ...     @property
    ...     def message(self):
    ...         right_of_info = Region(
    ...             x=self._info.region.right, y=self._info.region.y,
    ...             width=390, height=self._info.region.height)
    ...         return ocr(region=right_of_info, frame=self._frame) \
    ...                .replace('\n', ' ')
    ...
    ...     @property
    ...     def _info(self):
    ...         return match('../tests/info.png', frame=self._frame)

    Let's take this line by line::

        class Dialog(FrameObject):

    We create a class deriving from the ``FrameObject`` base class.

    ::

        @property
        def is_visible(self):
            return bool(self._info)

    All Frame Objects must define the ``is_visible`` property, which will
    determine the truthiness of the object. Returning True from this property
    indicates that this Frame Object class can be used with the provided frame
    and that the values of the other properties are likely to be valid.

    In this example we only return True if we see the "info" icon that appears
    on each dialog box. The actual work is delegated to the private property
    ``_info`` defined below.

    It's a good idea to return simple types from these properties rather than a
    `MatchResult`, to make the ``__repr__`` cleaner and to preserve equality
    properties.

    ::

        @property
        def title(self):
            return ocr(region=Region(396, 249, 500, 50), frame=self._frame)

    The base class provides a ``self._frame`` member. Here we're using
    `stbt.ocr` to extract the dialog's title text from this frame. This is the
    basic form that many Frame Object properties will take.

    This property demonstrates an advantage of Frame Objects. Your testcases
    now look like this::

        assert Dialog().title == "Information"

    instead of this::

        assert stbt.ocr(region=stbt.Region(396, 249, 500, 50)) == "Information"

    This is clearer because it reveals the intention of the testcase author
    (we're looking for the word in the *title* of the dialog). It is also
    easier (cheaper) to maintain: If the position of the title moves, you only
    need to update the implementation of ``Dialog.title``; you won't need to
    change any of your testcases.

    When defining Frame Objects you must take care to pass ``self._frame`` into
    every call to an image processing function (like our ``title`` property
    does when it calls ``ocr``, above). Otherwise the return values won't
    correspond to the frame you were expecting.

    ::

        @property
        def message(self):
            right_of_info = Region(
                x=self._info.region.right, y=self._info.region.y,
                width=390, height=self._info.region.height)
            return ocr(region=right_of_info, frame=self._frame) \
                   .replace('\n', ' ')

    This property demonstrates an advantage of Frame Objects over stand-alone
    helper functions. We are using the position of the "info" icon to find this
    message. Because the private ``_info`` property is shared between this
    property and ``is_visible`` we don't need to compute it twice -- the
    ``FrameObject`` base class will remember the value from the first time it
    was computed.

    ::

        @property
        def _info(self):
            return match('../tests/info.png', frame=self._frame)

    This is a private property because its name starts with ``_``. It will not
    appear in ``__repr__`` nor count toward equality comparisons, but the
    result from it will still be cached. This is useful for sharing
    intermediate values between your public properties, particularly if they
    are expensive to calculate. In this example we use ``_info`` from
    ``is_visible`` and ``message``.

    You wouldn't want this to be a public property because it returns a
    `MatchResult` which includes the entire frame passed into `match`.

    **Using our new Frame Object class**

    The default constructor will grab a frame from the device-under-test. This
    allows you to use Frame Objects with `wait_until` like this::

        dialog = wait_until(Dialog)
        assert 'great' in dialog.message

    We can also explicitly pass in a frame. This is mainly useful for
    unit-testing your Frame Objects.

    The examples below will use these example frames:

    .. testsetup::

        >>> from tests.test_frame_object import _load_frame
        >>> dialog = Dialog(frame=_load_frame('with-dialog'))
        >>> dialog_fab = Dialog(frame=_load_frame('with-dialog2'))
        >>> no_dialog = Dialog(frame=_load_frame('without-dialog'))
        >>> dialog_bunnies = Dialog(_load_frame('with-dialog-different-background'))
        >>> no_dialog_bunnies = Dialog(_load_frame('without-dialog-different-background'))

    .. |dialog| image:: images/frame-object-with-dialog.png
    .. |dialog_fab| image:: images/frame-object-with-dialog2.png
    .. |no_dialog| image:: images/frame-object-without-dialog.png
    .. |dialog_bunnies| image:: images/frame-object-with-dialog-different-background.png
    .. |no_dialog_bunnies| image:: images/frame-object-without-dialog-different-background.png

    +---------------------+---------------------+
    | dialog              | no_dialog           |
    |                     |                     |
    | |dialog|            | |no_dialog|         |
    +---------------------+---------------------+
    | dialog_bunnies      | no_dialog_bunnies   |
    |                     |                     |
    | |dialog_bunnies|    | |no_dialog_bunnies| |
    +---------------------+---------------------+
    | dialog_fab          |                     |
    |                     |                     |
    | |dialog_fab|        |                     |
    +---------------------+---------------------+

    Some basic operations:

    >>> print dialog.message
    This set-top box is great
    >>> print dialog_fab.message
    This set-top box is fabulous

    ``FrameObject`` defines truthiness of your objects based on the mandatory
    ``is_visible`` property:

    >>> bool(dialog)
    True
    >>> bool(no_dialog)
    False

    If ``is_visible`` is falsey, all the rest of the properties will be
    ``None``:

    >>> print no_dialog.message
    None

    This enables usage like::

        assert wait_until(lambda: Dialog().title == 'Information')

    ``FrameObject`` defines ``__repr__`` so that you don't have to. It looks
    like this:

    >>> dialog
    Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')
    >>> dialog_fab
    Dialog(is_visible=True, message=u'This set-top box is fabulous', title=u'Information')
    >>> no_dialog
    Dialog(is_visible=False)

    This makes it convenient to use doctests for unit-testing your Frame
    Objects.

    Frame Objects with identical property values are equal, even if the backing
    frames are not:

    >>> assert dialog == dialog
    >>> assert dialog == dialog_bunnies
    >>> assert dialog != dialog_fab
    >>> assert dialog != no_dialog

    This can be useful for detecting changes in the UI (while ignoring live TV
    in the background) or waiting for the UI to stop changing before
    interrogating it.

    All falsey Frame Objects of the same type are equal:

    >>> assert no_dialog == no_dialog
    >>> assert no_dialog == no_dialog_bunnies

    ``FrameObject`` defines ``__hash__`` too so you can store them in a set or
    in a dict:

    >>> {dialog}
    set([Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')])
    >>> len({no_dialog, dialog, dialog, dialog_bunnies})
    2
    '''
    def __init__(self, frame=None):
        if frame is None:
            frame = _dut.get_frame()
        super(FrameObject, self).__init__(frame)


@contextmanager
def _set_dut_singleton(dut):
    global _dut
    old_dut = dut
    try:
        _dut = dut
        yield dut
    finally:
        _dut = old_dut
