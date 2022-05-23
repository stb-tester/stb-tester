import os
import subprocess
from collections import namedtuple
from textwrap import dedent

import pytest

from stbt_core import wait_until
from _stbt.control import uri_to_control
from _stbt.utils import named_temporary_directory, scoped_process

# pylint:disable=redefined-outer-name


@pytest.fixture(scope="function")
def lircd():
    with named_temporary_directory("stbt-lirc-test") as tmpdir:
        socket = os.path.join(tmpdir, "lircd.socket")
        logfile = os.path.join(tmpdir, "lircd.log")
        proc = subprocess.Popen(
            ["lircd", "--nodaemon", "--loglevel=info", "--logfile=/dev/stderr",
             "--driver=file", "--device", logfile,  # lircd output
             "--output", socket,  # lircd reads instructions from here
             "--pidfile=%s/lircd.pid" % tmpdir,
             _find_file("Apple_TV.lircd.conf")])
        wait_until(lambda: (
            os.path.exists(socket) or proc.poll() is not None))

        with scoped_process(proc):
            yield namedtuple("Lircd", "socket logfile")(socket, logfile)


@pytest.mark.parametrize("key", [b'KEY_OK', 'KEY_OK'])
def test_press(lircd, key):
    logfile = open(lircd.logfile, encoding="utf-8")

    print("key = %r (%s)" % (key, type(key)))
    control = uri_to_control("lirc:%s:Apple_TV" % lircd.socket)
    control.press(key)
    lircd_output = logfile.read()
    expected = dedent("""\
        pulse 9000
        space 4500
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 527
        pulse 527
        space 527
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 1703
        pulse 527
        space 527
        pulse 527
        space 38000
        """)
    assert expected == lircd_output


def test_press_with_unknown_remote(lircd):
    control = uri_to_control("lirc:%s:roku" % lircd.socket)
    with pytest.raises(RuntimeError) as excinfo:
        control.press("KEY_OK")
    assert 'unknown remote: "roku"' in str(excinfo.value)


def test_press_with_unknown_key(lircd):
    control = uri_to_control("lirc:%s:Apple_TV" % lircd.socket)
    with pytest.raises(RuntimeError) as excinfo:
        control.press("KEY_MAGIC")
    assert 'unknown command: "KEY_MAGIC"' in str(excinfo.value)


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)
