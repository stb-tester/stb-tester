"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import annotations

import argparse
import datetime
import sys
import typing
import threading
import warnings
import weakref
from collections import deque, namedtuple
from contextlib import contextmanager
from enum import Enum

import cv2
import gi

from _stbt import cv2_compat
from _stbt import logging
from _stbt.config import get_config
from _stbt.gst_utils import array_from_sample, gst_sample_make_writable
from _stbt.imgutils import Frame
from _stbt.logging import _Annotation, debug, warn
from _stbt.types import Keypress, NoVideo, Region
from _stbt.utils import to_unicode

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # pylint:disable=wrong-import-order

Gst.init(None)

if typing.TYPE_CHECKING:
    # pylint:disable=unused-import
    from _stbt.control import RemoteControl
    # pylint:enable=unused-import

warnings.filterwarnings(
    action="default", category=DeprecationWarning, module=r"_stbt")

# Functions available to stbt scripts
# ===========================================================================


def new_device_under_test_from_config(parsed_args=None):
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

    display = [None]

    def raise_in_user_thread(exception):
        display[0].tell_user_thread(exception)
    mainloop = _mainloop()

    if not args.sink_pipeline and not args.save_video:
        sink_pipeline = NoSinkPipeline()
    else:
        sink_pipeline = SinkPipeline(  # pylint: disable=redefined-variable-type
            args.sink_pipeline, raise_in_user_thread, args.save_video)

    display[0] = Display(args.source_pipeline, sink_pipeline)
    return DeviceUnderTest(
        display=display[0], control=uri_to_control(args.control, display[0]),
        sink_pipeline=sink_pipeline, mainloop=mainloop)


class DeviceUnderTest():
    def __init__(self, display=None, control=None, sink_pipeline=None,
                 mainloop=None, _time=None):
        if _time is None:
            import time as _time
        self._time_of_last_press: float = 0
        self._display: Display = display
        self._control: RemoteControl = control
        self._sink_pipeline: SinkPipeline = sink_pipeline
        self._mainloop: typing.ContextManager[None] = mainloop
        self._time = _time
        self._last_keypress: Keypress | None = None

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

    def last_keypress(self):
        return self._last_keypress

    def press(self, key, interpress_delay_secs=None, hold_secs=None):
        if isinstance(key, Enum):
            key = key.value
        if section := get_config("control", "keymap_section", None):
            mapped_key = get_config(section, key, default=key)
        else:
            mapped_key = key

        if hold_secs is not None and hold_secs > 60:
            # You must ensure that lircd's --repeat-max is set high enough.
            raise ValueError("press: hold_secs must be less than 60 seconds")

        if hold_secs is None:
            with self._interpress_delay(interpress_delay_secs):
                if self._display is None:
                    frame_before = None
                else:
                    frame_before = self.get_frame()
                out = Keypress(key, self._time.time(), None, frame_before)
                self._control.press(mapped_key)
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
        if isinstance(key, Enum):
            key = key.value
        if section := get_config("control", "keymap_section", None):
            mapped_key = get_config(section, key, default=key)
        else:
            mapped_key = key

        with self._interpress_delay(interpress_delay_secs):
            out = Keypress(key, self._time.time(), None, self.get_frame())
            try:
                self._control.keydown(mapped_key)
                self.draw_text("Holding %s" % key, duration_secs=3)
                self._last_keypress = out
                yield out
            except:
                exc_info = sys.exc_info()
                try:
                    self._control.keyup(mapped_key)
                    self.draw_text("Released %s" % key, duration_secs=3)
                except Exception:  # pylint:disable=broad-except
                    # Don't mask original exception from the test script.
                    pass
                raise exc_info[1].with_traceback(exc_info[2])
            else:
                self._control.keyup(mapped_key)
                out.end_time = self._time.time()
                self.draw_text("Released %s" % key, duration_secs=3)

    @contextmanager
    def _interpress_delay(self, interpress_delay_secs):
        if interpress_delay_secs is None:
            interpress_delay_secs = get_config(
                "press", "interpress_delay_secs", type_=float)
        # `sleep` is inside a `while` loop because the actual suspension
        # time of `sleep` may be less than that requested.
        while True:
            seconds_to_wait = (
                self._time_of_last_press - self._time.time() +
                interpress_delay_secs)
            if seconds_to_wait > 0:
                self._time.sleep(seconds_to_wait)
            else:
                break

        try:
            yield
        finally:
            self._time_of_last_press = self._time.time()

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

        for i in range(max_presses + 1):
            try:
                return wait_for_match(image, timeout_secs=interval_secs,
                                      match_parameters=match_parameters,
                                      region=region, frames=self.frames())
            except MatchTimeout:
                if i == max_presses:
                    raise
            self.press(key)

    def frames(self, timeout_secs=None):
        if timeout_secs is not None:
            end_time = self._time.time() + timeout_secs
        timestamp = None
        first = True

        while True:
            frame = self._display.get_frame(
                max(10, timeout_secs or 0), since=timestamp)
            timestamp = frame.time

            if not first and timeout_secs is not None and timestamp > end_time:
                debug("timed out: %.3f > %.3f" % (timestamp, end_time))
                return

            yield frame
            first = False

    def get_frame(self):
        if self._display is None:
            raise RuntimeError(
                "stbt.get_frame(): Video capture has not been initialised")
        return self._display.get_frame()


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
              "is still alive!" if thread.is_alive() else "ok"))


def _draw_annotation(img, annotation):
    if not annotation.region:
        return
    cv2.rectangle(
        img, (annotation.region.x, annotation.region.y),
        (annotation.region.right, annotation.region.bottom), annotation.colour,
        thickness=3)

    # Slightly above the match annotation
    label_loc = (annotation.region.x, annotation.region.y - 10)
    _draw_text(img, annotation.label, label_loc, (255, 255, 255),
               font_scale=0.5)


class _TextAnnotation(namedtuple("_TextAnnotation", "time text duration")):
    @property
    def end_time(self):
        return self.time + self.duration


class SinkPipeline():
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

        # Just used for logging:
        self._appsrc_was_full = False

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
        if self.sink_pipeline is not None:
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
        self._raise_in_user_thread(RuntimeError(
            "Error from sink pipeline: %s: %s\n%s" % (err, err.message, dbg)))

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
                debug("teardown: Sink pipeline not in state PLAYING: %r"
                      % (state,))
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
            img,
            datetime.datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-4],
            (10, 30), (255, 255, 255))
        for i, x in enumerate(reversed(current_texts)):
            origin = (10, (i + 2) * 30)
            age = float(now - x.time) / 3
            color = (int(255 * max([1 - age, 0.5])),) * 3
            _draw_text(img, x.text, origin, color)

        # Regions:
        for annotation in annotations:
            _draw_annotation(img, annotation)

        APPSRC_LIMIT_BYTES = 100 * 1024 * 1024  # 100MB
        if self.appsrc.props.current_level_bytes > APPSRC_LIMIT_BYTES:
            # appsrc is backed-up, perhaps something's gone wrong.  We don't
            # want to use up all RAM, so let's drop the buffer on the floor.
            if not self._appsrc_was_full:
                warn("sink pipeline appsrc is full, dropping buffers from now "
                     "on")
                self._appsrc_was_full = True
            return
        elif self._appsrc_was_full:
            debug("sink pipeline appsrc no longer full, pushing buffers again")
            self._appsrc_was_full = False

        self.appsrc.props.caps = sample.get_caps()
        self.appsrc.emit("push-buffer", sample.get_buffer())
        self._sample_count += 1

    def draw(self, obj, duration_secs=None, label=""):
        with self.annotations_lock:
            if isinstance(obj, str):
                start_time = self._time.time()
                text = (
                    to_unicode(
                        datetime.datetime.fromtimestamp(start_time).strftime(
                            "%H:%M:%S.%f")[:-4]) +
                    ' ' +
                    to_unicode(obj))
                self.text_annotations.append(
                    _TextAnnotation(start_time, text, duration_secs))
            elif isinstance(obj, logging.SourceRegion):
                # Backwards compatibility.  Consider changing this in the
                # future.
                pass
            elif hasattr(obj, "region") and hasattr(obj, "time"):
                annotation = _Annotation.from_result(obj, label=label)
                if annotation.time:
                    self.annotations.append(annotation)
            else:
                raise TypeError(
                    "Can't draw object of type '%s'" % type(obj).__name__)


class NoSinkPipeline():
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


class Display():
    def __init__(self, user_source_pipeline, sink_pipeline):

        import time

        self._condition = threading.Condition()  # Protects last_frame
        self.last_frame = None
        self.last_used_frame = None
        self.source_pipeline = None
        self.init_time = time.time()
        self.tearing_down = False

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

    def set_source_pipeline_playing(self):
        if (self.source_pipeline.set_state(Gst.State.PAUSED) ==
                Gst.StateChangeReturn.NO_PREROLL):
            # This is a live source, drop frames if we get behind
            self.source_pipeline.get_by_name('_stbt_raw_frames_queue') \
                .set_property('leaky', to_unicode('downstream'))
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
                elif isinstance(self.last_frame, NoVideo):
                    raise NoVideo(str(self.last_frame))
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
        raise NoVideo("No frames received in %ss" % (timeout_secs,))

    def on_new_sample(self, appsink):
        sample = appsink.emit("pull-sample")

        running_time = sample.get_segment().to_running_time(
            Gst.Format.TIME, sample.get_buffer().pts)
        sample.time = float(appsink.base_time + running_time) / 1e9

        if (sample.time > self.init_time + 31536000 or
                sample.time < self.init_time - 31536000):  # 1 year
            warn("Received frame with suspicious timestamp: %f. Check your "
                 "source-pipeline configuration." % sample.time)

        frame = array_from_sample(sample)
        frame.flags.writeable = False

        # See also: logging.draw_on
        frame._draw_sink = weakref.ref(self._sink_pipeline)
        self.tell_user_thread(frame)
        self._sink_pipeline.on_sample(sample)
        return Gst.FlowReturn.OK

    def tell_user_thread(self, frame_or_exception):
        # `self.last_frame` is how we communicate from this thread (the GLib
        # main loop) to the main application thread running the user's script.
        # Note that only this thread writes to self.last_frame.

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
        self.tell_user_thread(NoVideo(
            "Error from source pipeline: %s: %s\n%s" % (err, err.message, dbg)))

    def on_warning(self, _bus, message):
        assert message.type == Gst.MessageType.WARNING
        pipeline = self.source_pipeline
        if pipeline is not None:
            Gst.debug_bin_to_dot_file_with_ts(
                pipeline, Gst.DebugGraphDetails.ALL, "WARNING")
        err, dbg = message.parse_warning()
        warn("%s: %s\n%s\n" % (err, err.message, dbg))

    def on_eos_from_source_pipeline(self, _bus, _message):
        if not self.tearing_down:
            self.tell_user_thread(NoVideo("EOS from source pipeline"))

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
