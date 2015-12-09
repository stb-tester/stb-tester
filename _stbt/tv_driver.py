import os
import sys
from time import sleep

from _stbt.config import get_config
from _stbt.utils import mkdir_p


def _gen_video_cache_dir():
    cache_root = (os.environ.get("XDG_CACHE_HOME", None) or
                  os.environ.get("HOME") + '/.cache')
    return cache_root + '/stbt/camera-video-cache'


def _generate_video_if_not_exists(video, video_generator, format_):
    from os.path import isfile
    filename = "%s/%s.%s" % (_gen_video_cache_dir(), video, format_)
    if not isfile(filename):
        from _stbt.gst_utils import frames_to_video
        import tempfile
        sys.stderr.write(
            "Creating test video '%s'.  This only has to happen once but may "
            "take some time...\n" % filename)

        # Create the video atomically to avoid serving invalid mp4s
        tf = tempfile.NamedTemporaryFile(prefix=filename, delete=False)
        frame_caps, frame_generator = video_generator[video]
        frames_to_video(
            tf.name, frame_generator(), caps=frame_caps, container=format_)
        os.rename(tf.name, filename)

        sys.stderr.write("Test video generation complete.\n")
    return filename


def _get_external_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("192.0.2.0", 80))
    return s.getsockname()[0]


class _HTTPVideoServer(object):
    def __init__(self, video_generators, video_format):
        self._video_generators = dict(video_generators)
        self._video_format = video_format
        self._lighttpd_pid = None
        self._base_url = None

        self._start()

    def _start(self):
        from textwrap import dedent
        from tempfile import NamedTemporaryFile
        from subprocess import CalledProcessError, check_output, STDOUT
        from random import randint
        video_cache_dir = _gen_video_cache_dir()
        mkdir_p(video_cache_dir)
        lighttpd_config_file = NamedTemporaryFile(
            prefix='stbt-camera-lighttpd-', suffix='.conf', delete=False)
        pidfile = NamedTemporaryFile(
            prefix="stbt-camera-lighttpd-", suffix=".pidfile")
        # This is an awful way to start listening on a random port and not a
        # great way of tracking the sub-process.
        port = None
        while port is None:
            try:
                lighttpd_config_file.seek(0)
                lighttpd_config_file.truncate(0)
                try_port = randint(10000, 30000)
                lighttpd_config_file.write(dedent("""\
                    # This file is generated automatically by stb-tester.
                    # DO NOT EDIT.
                    server.document-root = "%s"

                    server.port = %i

                    server.pid-file            = "%s"

                    mimetype.assign = (
                      ".png" => "image/png",
                      ".mp4" => "video/mp4",
                      ".ts" => "video/MP2T"
                    )""") % (video_cache_dir, try_port, pidfile.name))
                lighttpd_config_file.flush()
                check_output(['lighttpd', '-f', lighttpd_config_file.name],
                             close_fds=True, stderr=STDOUT)
                port = try_port
            except CalledProcessError as e:
                if e.output.find('Address already in use') != -1:
                    pass
                else:
                    sys.stderr.write("lighttpd failed to start: %s\n" %
                                     e.output)
                    raise
        # lighttpd writes its pidfile out after forking rather than before
        # causing a race.  The real fix is to patch lighttpd to support socket
        # passing and then open the listening socket ourselves.
        while os.fstat(pidfile.fileno()).st_size == 0:
            sleep(0.1)
        self._lighttpd_pid = int(pidfile.read())
        self._base_url = "http://%s:%i/" % (_get_external_ip(), port)

    @property
    def mime_type(self):
        return {
            'mp4': 'video/mp4',
            'ts': 'video/MP2T',
        }[self._video_format]

    def __del__(self):
        from signal import SIGTERM
        from os import kill
        if self._lighttpd_pid:
            kill(self._lighttpd_pid, SIGTERM)

    def get_url(self, video):
        _generate_video_if_not_exists(video, self._video_generators,
                                      self._video_format)
        return "%s%s.%s" % (self._base_url, video, self._video_format)


class _AssumeTvDriver(object):
    def show(self, filename):
        sys.stderr.write("Assuming video %s is playing\n" % filename)

    def stop(self):
        sys.stderr.write("Assuming videos are no longer playing\n")


class _FakeTvDriver(object):
    """TV driver intended to be paired up with fake-video-src.py from the test
    directory"""
    def __init__(self, control_pipe, video_server):
        self.control_pipe = open(control_pipe, 'w')
        self.video_server = video_server

    def show(self, video):
        uri = self.video_server.get_url(video)
        self.control_pipe.write("%s\n" % uri)
        self.control_pipe.flush()

    def stop(self):
        self.control_pipe.write("stop\n")
        self.control_pipe.flush()


class _ManualTvDriver(object):
    def __init__(self, video_server):
        self.video_server = video_server

    def show(self, video):
        url = self.video_server.get_url(video)
        sys.stderr.write(
            "Please show %s video.  This can be found at %s\n" % (video, url) +
            "\n" +
            "Press <ENTER> when video is showing\n")
        sys.stdin.readline()
        sys.stderr.write("Thank you\n")

    def stop(self):
        sys.stderr.write("Please return TV back to original state\n")


class _AdbTvDriver(object):
    def __init__(self, video_server, adb_cmd=None):
        if adb_cmd is None:
            adb_cmd = ['adb']
        self.adb_cmd = adb_cmd
        self.video_server = video_server

    def show(self, video):
        import subprocess
        cmd = self.adb_cmd + [
            'shell', 'am', 'start',
            '-a', 'android.intent.action.VIEW',
            '-d', self.video_server.get_url(video),
            '-t', self.video_server.mime_type]
        subprocess.check_call(cmd, close_fds=True)

    def stop(self):
        pass


def add_argparse_argument(argparser):
    argparser.add_argument(
        "--tv-driver",
        help="Determines how to display videos on TV.\n\n"
             "    manual - Prompt the user then wait for confirmation.\n"
             "    assume - Assume the video is already playing (useful for "
             "scripting when passing a single test to be run).\n"
             "    fake:pipe_name - Used for testing\n"
             "    adb[:adb_command] - Control an android device over adb",
             default=get_config("camera", "tv_driver", "manual"))


def create_from_args(args, video_generator):
    return create_from_description(args.tv_driver, video_generator)


def create_from_description(desc, video_generator):
    def make_video_server():
        return _HTTPVideoServer(
            video_generator,
            video_format=get_config('camera', 'video_format'))

    if desc == 'assume':
        return _AssumeTvDriver()
    elif desc.startswith('fake:'):
        return _FakeTvDriver(desc[5:], make_video_server())
    elif desc == 'manual':
        return _ManualTvDriver(make_video_server())
    elif desc == 'adb':
        return _AdbTvDriver(make_video_server())
    elif desc.startswith('adb:'):
        import shlex
        return _AdbTvDriver(make_video_server(), shlex.split(desc[4:]))
    else:
        raise RuntimeError("Unknown video driver requested: %s" % desc)
