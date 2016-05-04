import sys
from contextlib import contextmanager

import gi
import numpy

from .gst_hacks import map_gst_sample

gi.require_version("Gst", "1.0")
from gi.repository import GObject, Gst  # isort:skip pylint: disable=E0611

Gst.init([])


@contextmanager
def numpy_from_sample(sample, readonly=False):
    """
    Allow the contents of a GstSample to be read (and optionally changed) as a
    numpy array.  The provided numpy array is a view onto the contents of the
    GstBuffer in the sample provided.  The data is only valid within the `with:`
    block where this contextmanager is used so the provided array should not
    be referenced outside the `with:` block.  If you want to use it elsewhere
    either copy the data with `numpy.ndarray.copy()` or reference the GstSample
    directly.

    A `numpy.ndarray` may be passed as sample, in which case this
    contextmanager is a no-op.  This makes it easier to create functions which
    will accept either numpy arrays or GstSamples providing a migration path
    for reducing copying in stb-tester.

    :param sample:   Either a GstSample or a `numpy.ndarray` containing the data
                     you wish to manipulate as a `numpy.ndarray`
    :param readonly: bool. Determines whether you want to just read or change
                     the data contained within sample.  If True the GstSample
                     passed must be writeable or ValueError will be raised.
                     Use `gst_sample_make_writable` to get a writable
                     `GstSample`.

    >>> s = Gst.Sample.new(Gst.Buffer.new_wrapped("hello"),
    ...                    Gst.Caps.from_string("video/x-raw"), None, None)
    >>> with numpy_from_sample(s) as a:
    ...     print a
    [104 101 108 108 111]
    """
    if isinstance(sample, numpy.ndarray):
        yield sample
        return
    if not isinstance(sample, Gst.Sample):
        raise TypeError("numpy_from_gstsample must take a Gst.Sample or a "
                        "numpy.ndarray.  Received a %s" % str(type(sample)))

    caps = sample.get_caps()
    flags = Gst.MapFlags.READ
    if not readonly:
        flags |= Gst.MapFlags.WRITE

    with map_gst_sample(sample, flags) as buf:
        array = numpy.frombuffer((buf), dtype=numpy.uint8)
        array.flags.writeable = not readonly
        if caps.get_structure(0).get_value('format') in ['BGR', 'RGB']:
            array.shape = (caps.get_structure(0).get_value('height'),
                           caps.get_structure(0).get_value('width'),
                           3)
        yield array


def test_that_mapping_a_sample_readonly_gives_a_readonly_array():
    Gst.init([])
    s = Gst.Sample.new(Gst.Buffer.new_wrapped("hello"),
                       Gst.Caps.from_string("video/x-raw"), None, None)
    with numpy_from_sample(s, readonly=True) as ro:
        try:
            ro[0] = 3
            assert False, 'Writing elements should have thrown'
        except (ValueError, RuntimeError):
            # Different versions of numpy raise different exceptions
            pass


def test_passing_a_numpy_ndarray_as_sample_is_a_noop():
    a = numpy.ndarray((5, 2))
    with numpy_from_sample(a) as m:
        assert a is m


def test_that_dimensions_of_array_are_according_to_caps():
    s = Gst.Sample.new(Gst.Buffer.new_wrapped(
        "row 1 4 px  row 2 4 px  row 3 4 px  "),
        Gst.Caps.from_string("video/x-raw,format=BGR,width=4,height=3"),
        None, None)
    with numpy_from_sample(s, readonly=True) as a:
        assert a.shape == (3, 4, 3)


def gst_sample_make_writable(sample):
    if sample.get_buffer().mini_object.is_writable():
        return sample
    else:
        return Gst.Sample.new(
            sample.get_buffer().copy_region(
                Gst.BufferCopyFlags.FLAGS | Gst.BufferCopyFlags.TIMESTAMPS |
                Gst.BufferCopyFlags.META | Gst.BufferCopyFlags.MEMORY, 0,
                sample.get_buffer().get_size()),
            sample.get_caps(),
            sample.get_segment(),
            sample.get_info())


def get_frame_timestamp(frame):
    if isinstance(frame, Gst.Sample):
        return frame.get_buffer().pts
    else:
        return None


def frames_to_video(outfilename, frames, caps="image/svg",
                    container="ts"):
    """Given a list (or generator) of video frames generates a video and writes
    it to disk.  The video is MPEG4 encoded, with a silent stereo audio track
    encoded as AAC.

    :param outfilename: The filename of the video that is to be created
    :param frames:      A list of frames of the format `[(data, duration), ...]`
                        where duration is in nanoseconds and data will
                        typically be a string.
    :param caps:        GStreamer caps description as a string that describes
                        the format of the data passed in as frames.
    :param container:   The container format to use.  Valid choices are `"ts"`
                        for mpeg-ts and `"mp4"`

    The video/audio format was chosen as it seems to be most supported by most
    TVs.

    This function is typically used to generate a video from a list of SVGs.
    You can define a generator that yields slightly different SVGs in a
    sequence and get a video out the other side.  It can also be used for
    simple slideshows, etc."""
    muxer = {'ts': 'mpegtsmux', 'mp4': 'mp4mux'}[container]
    pipeline = Gst.parse_launch(
        """
        appsrc name=videosrc format=time caps=%s,framerate=(fraction)25/1 !
          queue ! decodebin ! videoconvert !
          videorate ! video/x-raw,framerate=(fraction)25/1 ! queue !
          avenc_mpeg4 bitrate=3000000 ! mpeg4videoparse ! queue ! mux.
        appsrc name=audiosrc format=time
          caps=audio/x-raw,format=S16LE,channels=2,rate=48000,layout=interleaved
          ! audioconvert ! queue ! voaacenc ! aacparse ! queue ! mux.
        %s name=mux ! queue ! filesink location="%s" """ %
        (caps, muxer, outfilename))

    vsrc = pipeline.get_by_name('videosrc')
    asrc = pipeline.get_by_name('audiosrc')

    r = PipelineRunner(pipeline)

    t = 0
    for data, duration in frames:
        _appsrc_push_data(vsrc, data, t, duration)
        _appsrc_push_data(asrc, '\0\0\0\0' * int(duration * 48000 / Gst.SECOND),
                          t, duration)
        t += duration

    if t == 0:
        raise ValueError("Sequence argument frames must not be empty")
    _appsrc_push_data(vsrc, data, t, 0)  # pylint: disable=W0631

    vsrc.emit("end-of-stream")
    asrc.emit('end-of-stream')

    r.run()
    return 0


def _appsrc_push_data(appsrc, data, pts=0, duration=0):
    buf = Gst.Buffer.new_wrapped(data)
    buf.pts = pts
    buf.duration = duration
    appsrc.emit('push-buffer', buf)


class PipelineRunner(object):
    """Provides an easy way to run a pre-constructed Gstreamer pipeline much
    like gst-launch"""
    def __init__(self, pipeline, stop_pos=None):
        self.mainloop = GObject.MainLoop()
        self.err, self.dbg = None, None

        def on_error(_bus, message):
            self.err, self.dbg = message.parse_error()
            self.mainloop.quit()

        def on_warning(_bus, message):
            assert message.type == Gst.MessageType.WARNING
            _err, _dbg = message.parse_warning()
            sys.stderr.write("Warning: %s: %s\n%s\n" % (_err, _err.message,
                             _dbg))

        def on_eos(_bus, _message):
            pipeline.set_state(Gst.State.NULL)
            self.mainloop.quit()

        bus = pipeline.get_bus()
        bus.connect("message::eos", on_eos)
        bus.connect("message::error", on_error)
        bus.connect("message::warning", on_warning)
        bus.add_signal_watch()

        pipeline.set_state(Gst.State.PAUSED)

        if stop_pos is not None:
            pipeline.seek(
                1.0, Gst.Format.TIME, Gst.SeekFlags.SEGMENT |
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, Gst.SeekType.SET,
                0, Gst.SeekType.SET, stop_pos)

        pipeline.set_state(Gst.State.PLAYING)
        self.pipeline = pipeline

    def run(self):
        self.mainloop.run()
        if self.err is not None:
            raise RuntimeError("Error running pipeline: %s\n\n%s" %
                               (self.err, self.dbg))

    def __del__(self):
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline.get_state(0)
