import sys

from gi.repository import GObject, Gst  # pylint: disable=E0611

Gst.init([])


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
