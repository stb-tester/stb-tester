#!/usr/bin/python -u

import argparse
import os
import sys
import threading

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from _stbt import gst_utils, utils

Gst.init([])

USE_SHMSRC = True


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("socket", help="shmsrc socket")

    args = parser.parse_args(argv[1:])

    cache_root = (os.environ.get("XDG_CACHE_HOME", None) or
                  os.environ.get("HOME") + '/.cache')
    default_file = '%s/stbt/camera-video-cache/black.mp4' % cache_root

    if not os.path.exists(default_file):
        utils.mkdir_p(os.path.dirname(default_file))
        gst_utils.frames_to_video(
            default_file, [(bytearray([0, 0, 0]) * 1280 * 720, 5 * Gst.SECOND)],
            'video/x-raw,format=BGR,width=1280,height=720', 'mp4')

    default_uri = "file://" + default_file

    frame_bytes = 1280 * 720 * 3

    next_video = [default_uri]

    def about_to_finish(playbin):
        playbin.set_property('uri', next_video[0])
        next_video[0] = default_uri
        playbin.set_state(Gst.State.PLAYING)

    if USE_SHMSRC:
        pipeline_desc = (
            """\
            playbin name=pb audio-sink=fakesink uri=%s flags=0x00000791 \
            video-sink="videoconvert \
                ! video/x-raw,width=1280,height=720,format=RGB ! identity ! \
                shmsink wait-for-connection=true shm-size=%i max-lateness=-1 \
                        qos=false socket-path=%s blocksize=%i sync=true \
                        buffer-time=100000000" """
            % (default_uri, frame_bytes * 1000, args.socket, frame_bytes))
    else:
        pipeline_desc = (
            """playbin name=pb audio-sink=fakesink uri=%s flags=0x00000791 \
            video-sink="videoconvert ! timeoverlay ! xvimagesink sync=true" """
            % default_uri)

    playbin = Gst.parse_launch(pipeline_desc)

    playbin.connect("about-to-finish", about_to_finish)

    runner = gst_utils.PipelineRunner(playbin)
    gst_thread = threading.Thread(target=runner.run)
    gst_thread.daemon = True
    gst_thread.start()

    playbin.get_state(0)

    def set_uri(uri):
        print "=== Setting URI to", uri
        if uri == 'stop':
            next_video[0] = default_uri
        else:
            next_video[0] = uri
        playbin.seek(
            1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            Gst.SeekType.END, 0, Gst.SeekType.NONE, 0)

    while True:
        uri = sys.stdin.readline()
        if uri == '':
            break
        elif len(uri.strip()) > 0:
            set_uri(uri.strip())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
