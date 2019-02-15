# coding: utf-8
"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

import argparse
import datetime
import functools
import inspect
import sys
import threading
import traceback
import warnings
import weakref
from collections import deque, namedtuple
from contextlib import contextmanager

import cv2
import gi

import _stbt.cv2_compat as cv2_compat
from _stbt import logging
from _stbt.config import get_config
from _stbt.gst_utils import (array_from_sample, gst_iterate,
                             gst_sample_make_writable)
from _stbt.imgutils import _frame_repr, find_user_file, Frame, imread
from _stbt.logging import ddebug, debug, warn
from _stbt.types import Region, UITestError, UITestFailure

gi.require_version("Gst", "1.0")
from gi.repository import GLib, GObject, Gst  # pylint:disable=wrong-import-order

Gst.init(None)

warnings.filterwarnings(
    action="always", category=DeprecationWarning, message='.*stb-tester')


# Functions available to stbt scripts
# ===========================================================================


def load_image(filename, flags=None):
    """Find & read an image from disk.

    If given a relative filename, this will search in the directory of the
    Python file that called ``load_image``, then in the directory of that
    file's caller, etc. This allows you to use ``load_image`` in a helper
    function, and then call that helper function from a different Python file
    passing in a filename relative to the caller.

    Finally this will search in the current working directory. This allows
    loading an image that you had previously saved to disk during the same
    test run.

    This is the same lookup algorithm used by `stbt.match` and similar
    functions.

    :type filename: str or unicode
    :param filename: A relative or absolute filename.

    :param flags: Flags to pass to :ocv:pyfunc:`cv2.imread`.

    :returns: An image in OpenCV format — that is, a `numpy.ndarray` of 8-bit
        values. With the default ``flags`` parameter this will be 3 channels
        BGR, or 4 channels BGRA if the file has transparent pixels.
    :raises: `IOError` if the specified path doesn't exist or isn't a valid
        image file.

    * Added in v28.
    * Changed in v30: Include alpha (transparency) channel if the file has
      transparent pixels.
    """

    absolute_filename = find_user_file(filename)
    if not absolute_filename:
        raise IOError("No such file: %s" % filename)
    image = imread(absolute_filename, flags)
    if image is None:
        raise IOError("Failed to load image: %s" % absolute_filename)
    return image


def new_device_under_test_from_config(
        parsed_args=None, transformation_pipeline=None):
    """
    `parsed_args` if present should come from calling argparser().parse_args().
    """
    from _stbt.control import uri_to_control

    if parsed_args is None:
        args = argparser().parse_args([])
    else:
        args = parsed_args

    if args.source_pipeline is None:
        args.source_pipeline = get_config('global', 'source_pipeline')
    if args.sink_pipeline is None:
        args.sink_pipeline = get_config('global', 'sink_pipeline')
    if args.control is None:
        args.control = get_config('global', 'control')
    if args.save_video is None:
        args.save_video = False
    if args.restart_source is None:
        args.restart_source = get_config('global', 'restart_source', type_=bool)
    if transformation_pipeline is None:
        transformation_pipeline = get_config('global',
                                             'transformation_pipeline')
    source_teardown_eos = get_config('global', 'source_teardown_eos',
                                     type_=bool)

    display = [None]

    def raise_in_user_thread(exception):
        display[0].tell_user_thread(exception)
    mainloop = _mainloop()

    if not args.sink_pipeline and not args.save_video:
        sink_pipeline = NoSinkPipeline()
    else:
        sink_pipeline = SinkPipeline(  # pylint: disable=redefined-variable-type
            args.sink_pipeline, raise_in_user_thread, args.save_video)

    display[0] = Display(
        args.source_pipeline, sink_pipeline, args.restart_source,
        transformation_pipeline, source_teardown_eos)
    return DeviceUnderTest(
        display=display[0], control=uri_to_control(args.control, display[0]),
        sink_pipeline=sink_pipeline, mainloop=mainloop)


class DeviceUnderTest(object):
    def __init__(self, display=None, control=None, sink_pipeline=None,
                 mainloop=None, _time=None):
        if _time is None:
            import time as _time
        self._time_of_last_press = None
        self._display = display
        self._control = control
        self._sink_pipeline = sink_pipeline
        self._mainloop = mainloop
        self._time = _time
        self._last_keypress = None

    def __enter__(self):
        if self._display:
            self._mainloop.__enter__()
            self._sink_pipeline.__enter__()
            self._display.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if self._display:
            self._sink_pipeline.exit_prep()
            self._display.__exit__(exc_type, exc_value, tb)
            self._display = None
            self._sink_pipeline.__exit__(exc_type, exc_value, tb)
            self._sink_pipeline = None
            self._mainloop.__exit__(exc_type, exc_value, tb)
        self._control = None

    def press(self, key, interpress_delay_secs=None, hold_secs=None):
        if hold_secs is not None and hold_secs > 60:
            # You must ensure that lircd's --repeat-max is set high enough.
            raise ValueError("press: hold_secs must be less than 60 seconds")

        if hold_secs is None:
            with self._interpress_delay(interpress_delay_secs):
                out = _Keypress(key, self._time.time(), None, self.get_frame())
                self._control.press(key)
                out.end_time = self._time.time()
            self.draw_text(key, duration_secs=3)
            self._last_keypress = out
            return out
        else:
            with self.pressing(key, interpress_delay_secs) as out:
                self._time.sleep(hold_secs)
            return out

    @contextmanager
    def pressing(self, key, interpress_delay_secs=None):
        with self._interpress_delay(interpress_delay_secs):
            out = _Keypress(key, self._time.time(), None, self.get_frame())
            try:
                self._control.keydown(key)
                self.draw_text("Holding %s" % key, duration_secs=3)
                self._last_keypress = out
                yield out
            except:  # pylint:disable=bare-except
                exc_info = sys.exc_info()
                try:
                    self._control.keyup(key)
                    self.draw_text("Released %s" % key, duration_secs=3)
                except Exception:  # pylint:disable=broad-except
                    # Don't mask original exception from the test script.
                    pass
                raise exc_info[0], exc_info[1], exc_info[2]
            else:
                self._control.keyup(key)
                out.end_time = self._time.time()
                self.draw_text("Released %s" % key, duration_secs=3)

    @contextmanager
    def _interpress_delay(self, interpress_delay_secs):
        if interpress_delay_secs is None:
            interpress_delay_secs = get_config(
                "press", "interpress_delay_secs", type_=float)
        if self._time_of_last_press is not None:
            # `sleep` is inside a `while` loop because the actual suspension
            # time of `sleep` may be less than that requested.
            while True:
                seconds_to_wait = (
                    self._time_of_last_press - datetime.datetime.now() +
                    datetime.timedelta(seconds=interpress_delay_secs)
                ).total_seconds()
                if seconds_to_wait > 0:
                    self._time.sleep(seconds_to_wait)
                else:
                    break

        try:
            yield
        finally:
            self._time_of_last_press = datetime.datetime.now()

    def draw_text(self, text, duration_secs=3):
        self._sink_pipeline.draw(text, duration_secs)

    def press_until_match(
            self,
            key,
            image,
            interval_secs=None,
            max_presses=None,
            match_parameters=None,
            region=Region.ALL):
        from .match import MatchParameters, MatchTimeout, wait_for_match
        if interval_secs is None:
            # Should this be float?
            interval_secs = get_config(
                "press_until_match", "interval_secs", type_=int)
        if max_presses is None:
            max_presses = get_config(
                "press_until_match", "max_presses", type_=int)

        if match_parameters is None:
            match_parameters = MatchParameters()

        i = 0

        while True:
            try:
                return wait_for_match(image, timeout_secs=interval_secs,
                                      match_parameters=match_parameters,
                                      region=region, frames=self.frames())
            except MatchTimeout:
                if i < max_presses:
                    self.press(key)
                    i += 1
                else:
                    raise

    def frames(self, timeout_secs=None):
        if timeout_secs is not None:
            end_time = self._time.time() + timeout_secs
        timestamp = None
        first = True

        while True:
            ddebug("user thread: Getting sample at %s" % self._time.time())
            frame = self._display.get_frame(
                max(10, timeout_secs), since=timestamp)
            ddebug("user thread: Got sample at %s" % self._time.time())
            timestamp = frame.time

            if not first and timeout_secs is not None and timestamp > end_time:
                debug("timed out: %.3f > %.3f" % (timestamp, end_time))
                return

            yield frame
            first = False

    def get_frame(self):
        return self._display.get_frame()


class _Keypress(object):
    def __init__(self, key, start_time, end_time, frame_before):
        self.key = key
        self.start_time = start_time
        self.end_time = end_time
        self.frame_before = frame_before

    def __repr__(self):
        return (
            "_Keypress(key=%r, start_time=%r, end_time=%r, frame_before=%s)" % (
                self.key, self.start_time, self.end_time,
                _frame_repr(self.frame_before)))


# Utility functions
# ===========================================================================


def save_frame(image, filename):
    """Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    cv2.imwrite(filename, image)


def wait_until(callable_, timeout_secs=10, interval_secs=0, predicate=None,
               stable_secs=0):
    """Wait until a condition becomes true, or until a timeout.

    Calls ``callable_`` repeatedly (with a delay of ``interval_secs`` seconds
    between successive calls) until it succeeds (that is, it returns a
    `truthy`_ value) or until ``timeout_secs`` seconds have passed.

    .. _truthy: https://docs.python.org/2/library/stdtypes.html#truth-value-testing

    :param callable_: any Python callable (such as a function or a lambda
        expression) with no arguments.

    :type timeout_secs: int or float, in seconds
    :param timeout_secs: After this timeout elapses, ``wait_until`` will return
        the last value that ``callable_`` returned, even if it's falsey.

    :type interval_secs: int or float, in seconds
    :param interval_secs: Delay between successive invocations of ``callable_``.

    :param predicate: A function that takes a single value. It will be given
        the return value from ``callable_``. The return value of *this* function
        will then be used to determine truthiness. If the predicate test
        succeeds, ``wait_until`` will still return the original value from
        ``callable_``, not the predicate value.

    :type stable_secs: int or float, in seconds
    :param stable_secs: Wait for ``callable_``'s return value to remain the same
        (as determined by ``==``) for this duration before returning. If
        ``predicate`` is also given, the values returned from ``predicate``
        will be compared.

    :returns: The return value from ``callable_`` (which will be truthy if it
        succeeded, or falsey if ``wait_until`` timed out). If the value was
        truthy when the timeout was reached but it failed the ``predicate`` or
        ``stable_secs`` conditions (if any) then ``wait_until`` returns
        ``None``.

    After you send a remote-control signal to the device-under-test it usually
    takes a few frames to react, so a test script like this would probably
    fail::

        press("KEY_EPG")
        assert match("guide.png")

    Instead, use this::

        press("KEY_EPG")
        assert wait_until(lambda: match("guide.png"))

    Note that instead of the above ``assert wait_until(...)`` you could use
    ``wait_for_match("guide.png")``. ``wait_until`` is a generic solution that
    also works with stbt's other functions, like `match_text` and
    `is_screen_black`.

    ``wait_until`` allows composing more complex conditions, such as::

        # Wait until something disappears:
        assert wait_until(lambda: not match("xyz.png"))

        # Assert that something doesn't appear within 10 seconds:
        assert not wait_until(lambda: match("xyz.png"))

        # Assert that two images are present at the same time:
        assert wait_until(lambda: match("a.png") and match("b.png"))

        # Wait but don't raise an exception:
        if not wait_until(lambda: match("xyz.png")):
            do_something_else()

        # Wait for a menu selection to change. Here ``Menu`` is a `FrameObject`
        # with a property called `selection` that returns a string with the
        # name of the currently-selected menu item:
        # The return value (``menu``) is an instance of ``Menu``.
        menu = wait_until(Menu, predicate=lambda x: x.selection == "Home")

        # Wait for a match to stabilise position, returning the first stable
        # match. Used in performance measurements, for example to wait for a
        # selection highlight to finish moving:
        press("KEY_DOWN")
        start_time = time.time()
        match_result = wait_until(lambda: stbt.match("selection.png"),
                                  predicate=lambda x: x and x.region,
                                  stable_secs=2)
        assert match_result
        end_time = match_result.time  # this is the first stable frame
        print "Transition took %s seconds" % (end_time - start_time)

    Added in v28: The ``predicate`` and ``stable_secs`` parameters.
    """
    import time

    if predicate is None:
        predicate = lambda x: x
    stable_value = None
    stable_predicate_value = None
    expiry_time = time.time() + timeout_secs

    while True:
        t = time.time()
        value = callable_()
        predicate_value = predicate(value)

        if stable_secs:
            if predicate_value != stable_predicate_value:
                stable_since = t
                stable_value = value
                stable_predicate_value = predicate_value
            if predicate_value and t - stable_since >= stable_secs:
                return stable_value
        else:
            if predicate_value:
                return value

        if t >= expiry_time:
            debug("wait_until timed out: %s" % _callable_description(callable_))
            if not value:
                return value  # it's falsey
            else:
                return None  # must have failed stable_secs or predicate checks

        time.sleep(interval_secs)


def _callable_description(callable_):
    """Helper to provide nicer debug output when `wait_until` fails.

    >>> _callable_description(wait_until)
    'wait_until'
    >>> _callable_description(
    ...     lambda: stbt.press("OK"))
    '    lambda: stbt.press("OK"))\\n'
    >>> _callable_description(functools.partial(int, base=2))
    'int'
    >>> _callable_description(functools.partial(functools.partial(int, base=2),
    ...                                         x='10'))
    'int'
    >>> class T(object):
    ...     def __call__(self): return True;
    >>> _callable_description(T())
    '<_stbt.core.T object at 0x...>'
    """
    if hasattr(callable_, "__name__"):
        name = callable_.__name__
        if name == "<lambda>":
            try:
                name = inspect.getsource(callable_)
            except IOError:
                pass
        return name
    elif isinstance(callable_, functools.partial):
        return _callable_description(callable_.func)
    else:
        return repr(callable_)


@contextmanager
def as_precondition(message):
    """Context manager that replaces test failures with test errors.

    Stb-tester's reports show test failures (that is, `UITestFailure` or
    `AssertionError` exceptions) as red results, and test errors (that is,
    unhandled exceptions of any other type) as yellow results. Note that
    `wait_for_match`, `wait_for_motion`, and similar functions raise a
    `UITestFailure` when they detect a failure. By running such functions
    inside an `as_precondition` context, any `UITestFailure` or
    `AssertionError` exceptions they raise will be caught, and a
    `PreconditionError` will be raised instead.

    When running a single testcase hundreds or thousands of times to reproduce
    an intermittent defect, it is helpful to mark unrelated failures as test
    errors (yellow) rather than test failures (red), so that you can focus on
    diagnosing the failures that are most likely to be the particular defect
    you are looking for. For more details see `Test failures vs. errors
    <http://stb-tester.com/preconditions>`__.

    :param str message:
        A description of the precondition. Word this positively: "Channels
        tuned", not "Failed to tune channels".

    :raises:
        `PreconditionError` if the wrapped code block raises a `UITestFailure`
        or `AssertionError`.

    Example::

        def test_that_the_on_screen_id_is_shown_after_booting():
            channel = 100

            with stbt.as_precondition("Tuned to channel %s" % channel):
                mainmenu.close_any_open_menu()
                channels.goto_channel(channel)
                power.cold_reboot()
                assert channels.is_on_channel(channel)

            stbt.wait_for_match("on-screen-id.png")

    """
    try:
        yield
    except (UITestFailure, AssertionError) as e:
        debug("stbt.as_precondition caught a %s exception and will "
              "re-raise it as PreconditionError.\nOriginal exception was:\n%s"
              % (type(e).__name__, traceback.format_exc(e)))
        exc = PreconditionError(message, e)
        if hasattr(e, 'screenshot'):
            exc.screenshot = e.screenshot  # pylint: disable=attribute-defined-outside-init,no-member
        raise exc


class NoVideo(Exception):
    """No video available from the source pipeline."""
    pass


class PreconditionError(UITestError):
    """Exception raised by `as_precondition`."""
    def __init__(self, message, original_exception):
        super(PreconditionError, self).__init__()
        self.message = message
        self.original_exception = original_exception

    def __str__(self):
        return (
            "Didn't meet precondition '%s' (original exception was: %s)"
            % (self.message, self.original_exception))


# stbt-run initialisation and convenience functions
# (you will need these if writing your own version of stbt-run)
# ===========================================================================

def argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--control',
        default=get_config('global', 'control'),
        help='The remote control to control the stb (default: %(default)s)')
    parser.add_argument(
        '--source-pipeline',
        default=get_config('global', 'source_pipeline'),
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.add_argument(
        '--sink-pipeline',
        default=get_config('global', 'sink_pipeline'),
        help='A gstreamer pipeline to use for video output '
             '(default: %(default)s)')
    parser.add_argument(
        '--restart-source', action='store_true',
        default=get_config('global', 'restart_source', type_=bool),
        help='Restart the GStreamer source pipeline when video loss is '
             'detected')
    parser.add_argument(
        '--save-video', help='Record video to the specified file',
        metavar='FILE', default=get_config('run', 'save_video'))

    logging.argparser_add_verbose_argument(parser)

    return parser


# Internal
# ===========================================================================


@contextmanager
def _mainloop():
    mainloop = GLib.MainLoop.new(context=None, is_running=False)

    thread = threading.Thread(target=mainloop.run)
    thread.daemon = True
    thread.start()

    try:
        yield
    finally:
        mainloop.quit()
        thread.join(10)
        debug("teardown: Exiting (GLib mainloop %s)" % (
              "is still alive!" if thread.isAlive() else "ok"))


class _Annotation(namedtuple("_Annotation", "time region label colour")):
    MATCHED = (32, 0, 255)  # Red
    NO_MATCH = (32, 255, 255)  # Yellow

    @staticmethod
    def from_result(result, label=""):
        colour = _Annotation.MATCHED if result else _Annotation.NO_MATCH
        return _Annotation(result.time, result.region, label, colour)

    def draw(self, img):
        if not self.region:
            return
        cv2.rectangle(
            img, (self.region.x, self.region.y),
            (self.region.right, self.region.bottom), self.colour,
            thickness=3)

        # Slightly above the match annotation
        label_loc = (self.region.x, self.region.y - 10)
        _draw_text(img, self.label, label_loc, (255, 255, 255), font_scale=0.5)


class _TextAnnotation(namedtuple("_TextAnnotation", "time text duration")):
    @property
    def end_time(self):
        return self.time + self.duration


class SinkPipeline(object):
    def __init__(self, user_sink_pipeline, raise_in_user_thread, save_video=""):
        import time as _time

        self.annotations_lock = threading.Lock()
        self.text_annotations = []
        self.annotations = []
        self._raise_in_user_thread = raise_in_user_thread
        self.received_eos = threading.Event()
        self._frames = deque(maxlen=35)
        self._time = _time
        self._sample_count = 0

        # The test script can draw on the video, but this happens in a different
        # thread.  We don't know when they're finished drawing so we just give
        # them 0.5s instead.
        self._sink_latency_secs = 0.5

        sink_pipeline_description = (
            "appsrc name=appsrc format=time is-live=true "
            "caps=video/x-raw,format=(string)BGR ")

        if save_video and user_sink_pipeline:
            sink_pipeline_description += "! tee name=t "
            src = "t. ! queue leaky=downstream"
        else:
            src = "appsrc."

        if save_video:
            if not save_video.endswith(".webm"):
                save_video += ".webm"
            debug("Saving video to '%s'" % save_video)
            sink_pipeline_description += (
                "{src} ! videoconvert ! "
                "vp8enc cpu-used=6 min_quantizer=32 max_quantizer=32 ! "
                "webmmux ! filesink location={save_video} ").format(
                src=src, save_video=save_video)

        if user_sink_pipeline:
            sink_pipeline_description += (
                "{src} ! videoconvert ! {user_sink_pipeline}").format(
                src=src, user_sink_pipeline=user_sink_pipeline)

        self.sink_pipeline = Gst.parse_launch(sink_pipeline_description)
        sink_bus = self.sink_pipeline.get_bus()
        sink_bus.connect("message::error", self._on_error)
        sink_bus.connect("message::warning", self._on_warning)
        sink_bus.connect("message::eos", self._on_eos_from_sink_pipeline)
        sink_bus.add_signal_watch()
        self.appsrc = self.sink_pipeline.get_by_name("appsrc")

        debug("sink pipeline: %s" % sink_pipeline_description)

    def _on_eos_from_sink_pipeline(self, _bus, _message):
        debug("Got EOS from sink pipeline")
        self.received_eos.set()

    def _on_warning(self, _bus, message):
        assert message.type == Gst.MessageType.WARNING
        Gst.debug_bin_to_dot_file_with_ts(
            self.sink_pipeline, Gst.DebugGraphDetails.ALL, "WARNING")
        err, dbg = message.parse_warning()
        warn("%s: %s\n%s\n" % (err, err.message, dbg))

    def _on_error(self, _bus, message):
        assert message.type == Gst.MessageType.ERROR
        if self.sink_pipeline is not None:
            Gst.debug_bin_to_dot_file_with_ts(
                self.sink_pipeline, Gst.DebugGraphDetails.ALL, "ERROR")
        err, dbg = message.parse_error()
        self._raise_in_user_thread(
            RuntimeError("%s: %s\n%s\n" % (err, err.message, dbg)))

    def __enter__(self):
        self.received_eos.clear()
        self.sink_pipeline.set_state(Gst.State.PLAYING)

    def exit_prep(self):
        # It goes sink.exit_prep, src.__exit__, sink.__exit__, so we can do
        # teardown things here that require the src to still be running.

        # Dropping the sink latency to 0 will cause all the frames in
        # self._frames to be pushed next time on_sample is called.  We can't
        # flush here because on_sample is called from the thread that is running
        # `Display`.
        self._sink_latency_secs = 0

        # Wait for up to 1s for the sink pipeline to get into the RUNNING state.
        # This is to avoid teardown races in the sink pipeline caused by buggy
        # GStreamer elements
        self.sink_pipeline.get_state(1 * Gst.SECOND)

    def __exit__(self, _1, _2, _3):
        # Drain the frame queue
        while self._frames:
            self._push_sample(self._frames.pop())

        if self._sample_count > 0:
            state = self.sink_pipeline.get_state(0)
            if (state[0] != Gst.StateChangeReturn.SUCCESS or
                    state[1] != Gst.State.PLAYING):
                debug(
                    "teardown: Sink pipeline not in state PLAYING: %r" % state)
            debug("teardown: Sending eos on sink pipeline")
            if self.appsrc.emit("end-of-stream") == Gst.FlowReturn.OK:
                self.sink_pipeline.send_event(Gst.Event.new_eos())
                if not self.received_eos.wait(10):
                    debug("Timeout waiting for sink EOS")
            else:
                debug("Sending EOS to sink pipeline failed")
        else:
            debug("SinkPipeline teardown: Not sending EOS, no samples sent")

        self.sink_pipeline.set_state(Gst.State.NULL)

        # Don't want to cause the Display object to hang around on our account,
        # we won't be raising any errors from now on anyway:
        self._raise_in_user_thread = None

    def on_sample(self, sample):
        """
        Called from `Display` for each frame.
        """
        now = sample.time
        self._frames.appendleft(sample)

        while self._frames:
            oldest = self._frames.pop()
            if oldest.time > now - self._sink_latency_secs:
                self._frames.append(oldest)
                break
            self._push_sample(oldest)

    def _push_sample(self, sample):
        # Calculate whether we need to draw any annotations on the output video.
        now = sample.time
        annotations = []
        with self.annotations_lock:
            # Remove expired annotations
            self.text_annotations = [x for x in self.text_annotations
                                     if now < x.end_time]
            current_texts = [x for x in self.text_annotations if x.time <= now]
            for annotation in list(self.annotations):
                if annotation.time == now:
                    annotations.append(annotation)
                if now >= annotation.time:
                    self.annotations.remove(annotation)

        sample = gst_sample_make_writable(sample)
        img = array_from_sample(sample, readwrite=True)
        # Text:
        _draw_text(
            img, datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4],
            (10, 30), (255, 255, 255))
        for i, x in enumerate(reversed(current_texts)):
            origin = (10, (i + 2) * 30)
            age = float(now - x.time) / 3
            color = (int(255 * max([1 - age, 0.5])),) * 3
            _draw_text(img, x.text, origin, color)

        # Regions:
        for annotation in annotations:
            annotation.draw(img)

        self.appsrc.props.caps = sample.get_caps()
        self.appsrc.emit("push-buffer", sample.get_buffer())
        self._sample_count += 1

    def draw(self, obj, duration_secs=None, label=""):
        with self.annotations_lock:
            if isinstance(obj, (str, unicode)):
                start_time = self._time.time()
                text = (
                    datetime.datetime.fromtimestamp(start_time).strftime(
                        "%H:%M:%S.%f")[:-4] +
                    ' ' + obj)
                self.text_annotations.append(
                    _TextAnnotation(start_time, text, duration_secs))
            elif hasattr(obj, "region") and hasattr(obj, "time"):
                annotation = _Annotation.from_result(obj, label=label)
                if annotation.time:
                    self.annotations.append(annotation)
            else:
                raise TypeError(
                    "Can't draw object of type '%s'" % type(obj).__name__)


class NoSinkPipeline(object):
    """
    Used in place of a SinkPipeline when no video output is required.  Is a lot
    faster because it doesn't do anything.  It especially doesn't do any copying
    nor video encoding :).
    """
    def __enter__(self):
        pass

    def exit_prep(self):
        pass

    def __exit__(self, _1, _2, _3):
        pass

    def on_sample(self, _sample):
        pass

    def draw(self, _obj, _duration_secs=None, label=""):
        pass


class Display(object):
    def __init__(self, user_source_pipeline, sink_pipeline,
                 restart_source=False, transformation_pipeline='identity',
                 source_teardown_eos=False):

        import time

        self._condition = threading.Condition()  # Protects last_frame
        self.last_frame = None
        self.last_used_frame = None
        self.source_pipeline = None
        self.init_time = time.time()
        self.underrun_timeout = None
        self.tearing_down = False
        self.restart_source_enabled = restart_source
        self.source_teardown_eos = source_teardown_eos

        appsink = (
            "appsink name=appsink max-buffers=1 drop=false sync=true "
            "emit-signals=true "
            "caps=video/x-raw,format=BGR")
        # Notes on the source pipeline:
        # * _stbt_raw_frames_queue is kept small to reduce the amount of slack
        #   (and thus the latency) of the pipeline.
        # * _stbt_user_data_queue before the decodebin is large.  We don't want
        #   to drop encoded packets as this will cause significant image
        #   artifacts in the decoded buffers.  We make the assumption that we
        #   have enough horse-power to decode the incoming stream and any delays
        #   will be transient otherwise it could start filling up causing
        #   increased latency.
        self.source_pipeline_description = " ! ".join([
            user_source_pipeline,
            'queue name=_stbt_user_data_queue max-size-buffers=0 '
            '    max-size-bytes=0 max-size-time=10000000000',
            "decodebin",
            'queue name=_stbt_raw_frames_queue max-size-buffers=2',
            'videoconvert',
            'video/x-raw,format=BGR',
            transformation_pipeline,
            appsink])
        self.create_source_pipeline()

        self._sink_pipeline = sink_pipeline

        debug("source pipeline: %s" % self.source_pipeline_description)

    def create_source_pipeline(self):
        self.source_pipeline = Gst.parse_launch(
            self.source_pipeline_description)
        source_bus = self.source_pipeline.get_bus()
        source_bus.connect("message::error", self.on_error)
        source_bus.connect("message::warning", self.on_warning)
        source_bus.connect("message::eos", self.on_eos_from_source_pipeline)
        source_bus.add_signal_watch()
        appsink = self.source_pipeline.get_by_name("appsink")
        appsink.connect("new-sample", self.on_new_sample)

        # A realtime clock gives timestamps compatible with time.time()
        self.source_pipeline.use_clock(
            Gst.SystemClock(clock_type=Gst.ClockType.REALTIME))

        if self.restart_source_enabled:
            # Handle loss of video (but without end-of-stream event) from the
            # Hauppauge HDPVR capture device.
            source_queue = self.source_pipeline.get_by_name(
                "_stbt_user_data_queue")
            source_queue.connect("underrun", self.on_underrun)
            source_queue.connect("running", self.on_running)

    def set_source_pipeline_playing(self):
        if (self.source_pipeline.set_state(Gst.State.PAUSED) ==
                Gst.StateChangeReturn.NO_PREROLL):
            # This is a live source, drop frames if we get behind
            self.source_pipeline.get_by_name('_stbt_raw_frames_queue') \
                .set_property('leaky', 'downstream')
            self.source_pipeline.get_by_name('appsink') \
                .set_property('sync', False)

        self.source_pipeline.set_state(Gst.State.PLAYING)

    def get_frame(self, timeout_secs=10, since=None):
        import time
        t = time.time()
        end_time = t + timeout_secs
        if since is None:
            # If you want to wait 10s for a frame you're probably not interested
            # in a frame from 10s ago.
            since = t - timeout_secs

        with self._condition:
            while True:
                if (isinstance(self.last_frame, Frame) and
                        self.last_frame.time > since):
                    self.last_used_frame = self.last_frame
                    return self.last_frame
                elif isinstance(self.last_frame, Exception):
                    raise RuntimeError(str(self.last_frame))
                t = time.time()
                if t > end_time:
                    break
                self._condition.wait(end_time - t)

        pipeline = self.source_pipeline
        if pipeline:
            Gst.debug_bin_to_dot_file_with_ts(
                pipeline, Gst.DebugGraphDetails.ALL, "NoVideo")
        raise NoVideo("No video")

    def on_new_sample(self, appsink):
        sample = appsink.emit("pull-sample")

        running_time = sample.get_segment().to_running_time(
            Gst.Format.TIME, sample.get_buffer().pts)
        sample.time = (
            float(appsink.base_time + running_time) / 1e9)

        if (sample.time > self.init_time + 31536000 or
                sample.time < self.init_time - 31536000):  # 1 year
            warn("Received frame with suspicious timestamp: %f. Check your "
                 "source-pipeline configuration." % sample.time)

        frame = array_from_sample(sample)
        frame.flags.writeable = False

        # See also: logging.draw_on
        frame._draw_sink = weakref.ref(self._sink_pipeline)  # pylint: disable=protected-access
        self.tell_user_thread(frame)
        self._sink_pipeline.on_sample(sample)
        return Gst.FlowReturn.OK

    def tell_user_thread(self, frame_or_exception):
        # `self.last_frame` is how we communicate from this thread (the GLib
        # main loop) to the main application thread running the user's script.
        # Note that only this thread writes to self.last_frame.

        if isinstance(frame_or_exception, Exception):
            ddebug("glib thread: reporting exception to user thread: %s" %
                   frame_or_exception)
        else:
            ddebug("glib thread: new sample (time=%s)." %
                   frame_or_exception.time)

        with self._condition:
            self.last_frame = frame_or_exception
            self._condition.notify_all()

    def on_error(self, _bus, message):
        assert message.type == Gst.MessageType.ERROR
        pipeline = self.source_pipeline
        if pipeline is not None:
            Gst.debug_bin_to_dot_file_with_ts(
                pipeline, Gst.DebugGraphDetails.ALL, "ERROR")
        err, dbg = message.parse_error()
        self.tell_user_thread(
            RuntimeError("%s: %s\n%s\n" % (err, err.message, dbg)))

    def on_warning(self, _bus, message):
        assert message.type == Gst.MessageType.WARNING
        Gst.debug_bin_to_dot_file_with_ts(
            self.source_pipeline, Gst.DebugGraphDetails.ALL, "WARNING")
        err, dbg = message.parse_warning()
        warn("%s: %s\n%s\n" % (err, err.message, dbg))

    def on_eos_from_source_pipeline(self, _bus, _message):
        if not self.tearing_down:
            warn("Got EOS from source pipeline")
            self.restart_source()

    def on_underrun(self, _element):
        if self.underrun_timeout:
            ddebug("underrun: I already saw a recent underrun; ignoring")
        else:
            ddebug("underrun: scheduling 'restart_source' in 2s")
            self.underrun_timeout = GObjectTimeout(2, self.restart_source)
            self.underrun_timeout.start()

    def on_running(self, _element):
        if self.underrun_timeout:
            ddebug("running: cancelling underrun timer")
            self.underrun_timeout.cancel()
            self.underrun_timeout = None
        else:
            ddebug("running: no outstanding underrun timers; ignoring")

    def restart_source(self, *_args):
        warn("Attempting to recover from video loss: "
             "Stopping source pipeline and waiting 5s...")
        self.source_pipeline.set_state(Gst.State.NULL)
        self.source_pipeline = None
        GObjectTimeout(5, self.start_source).start()
        return False  # stop the timeout from running again

    def start_source(self):
        if self.tearing_down:
            return False
        warn("Restarting source pipeline...")
        self.create_source_pipeline()
        self.set_source_pipeline_playing()
        warn("Restarted source pipeline")
        if self.restart_source_enabled:
            self.underrun_timeout.start()
        return False  # stop the timeout from running again

    @staticmethod
    def appsink_await_eos(appsink, timeout=None):
        done = threading.Event()

        def on_eos(_appsink):
            done.set()
            return True
        hid = appsink.connect('eos', on_eos)
        d = appsink.get_property('eos') or done.wait(timeout)
        appsink.disconnect(hid)
        return d

    def __enter__(self):
        self.set_source_pipeline_playing()

    def __exit__(self, _1, _2, _3):
        self.tearing_down = True
        self.source_pipeline, source = None, self.source_pipeline
        if source:
            if self.source_teardown_eos:
                debug("teardown: Sending eos on source pipeline")
                for elem in gst_iterate(source.iterate_sources()):
                    elem.send_event(Gst.Event.new_eos())
                if not self.appsink_await_eos(
                        source.get_by_name('appsink'), timeout=10):
                    debug("Source pipeline did not teardown gracefully")
            source.set_state(Gst.State.NULL)
            source = None


def _draw_text(numpy_image, text, origin, color, font_scale=1.0):
    if not text:
        return

    (width, height), _ = cv2.getTextSize(
        text, fontFace=cv2.FONT_HERSHEY_DUPLEX, fontScale=font_scale,
        thickness=1)
    cv2.rectangle(
        numpy_image, (origin[0] - 2, origin[1] + 2),
        (origin[0] + width + 2, origin[1] - height - 2),
        thickness=cv2_compat.FILLED, color=(0, 0, 0))
    cv2.putText(
        numpy_image, text, origin, cv2.FONT_HERSHEY_DUPLEX,
        fontScale=font_scale, color=color, lineType=cv2_compat.LINE_AA)


class GObjectTimeout(object):
    """Responsible for setting a timeout in the GTK main loop."""
    def __init__(self, timeout_secs, handler, *args):
        self.timeout_secs = timeout_secs
        self.handler = handler
        self.args = args
        self.timeout_id = None

    def start(self):
        self.timeout_id = GObject.timeout_add(
            self.timeout_secs * 1000, self.handler, *self.args)

    def cancel(self):
        if self.timeout_id:
            GObject.source_remove(self.timeout_id)
        self.timeout_id = None
