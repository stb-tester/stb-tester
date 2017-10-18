import os
import socket
import subprocess
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

import pytest

from _stbt.control import uri_to_remote
from _stbt.core import wait_until
from _stbt.utils import named_temporary_directory


# For py.test fixtures:
# pylint: disable=redefined-outer-name


@contextmanager
def scoped_process(process):
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@contextmanager
def scoped_path_addition(path):
    os.environ['PATH'] = "%s:%s" % (path, os.environ['PATH'])
    try:
        yield
    finally:
        if os.environ['PATH'] == "%s:" % path:
            os.environ['PATH'] = os.environ['PATH'][len(path) + 1:]


def srcdir(filename="", here=os.path.abspath(__file__)):
    return os.path.join(os.path.dirname(here), "..", filename)


@pytest.yield_fixture(scope='session')
def installed_stbt_control_relay():
    with named_temporary_directory("stbt-control-relay-install.XXXXXX") as tmp:
        oldprefix = open(srcdir(".stbt-prefix")).read()
        subprocess.check_call(
            ["make", "prefix=%s" % tmp, "install-stbt-control-relay"],
            cwd=srcdir())
        open(srcdir(".stbt-prefix"), 'w').write(oldprefix)

        os.environ['PATH'] = "%s/bin:%s" % (tmp, os.environ['PATH'])
        yield "%s/bin/stbt-control-relay" % tmp


@pytest.yield_fixture(scope='function')
def stbt_control_relay_on_path(installed_stbt_control_relay):
    with scoped_path_addition(os.path.dirname(installed_stbt_control_relay)):
        yield installed_stbt_control_relay


def test_stbt_control_relay(stbt_control_relay_on_path):  # pylint: disable=unused-argument
    with named_temporary_directory("stbt-control-relay-test.XXXXXX") as tmpdir:
        def t(filename):
            return os.path.join(tmpdir, filename)
        proc = subprocess.Popen(
            ["stbt-control-relay",
             "--socket", t("lircd.sock"),
             "file:" + t("one-file")])
        with scoped_process(proc):
            wait_until(lambda: (
                os.path.exists(t("lircd.sock")) or proc.poll() is not None))
            testremote = uri_to_remote("lirc:%s:stbt-test" % t("lircd.sock"))

            testremote.press("KEY_UP")
            testremote.press("KEY_DOWN")
            expected = "KEY_UP\nKEY_DOWN\n"

            assert open(t("one-file")).read() == expected


def socket_passing_setup(socket):
    def preexec_fn():
        fd = socket.fileno()
        os.environ['LISTEN_FDS'] = '1'
        os.environ['LISTEN_PID'] = str(os.getpid())
        if fd != 3:
            os.dup2(fd, 3)
        os.closerange(4, 100)

    return preexec_fn


def test_stbt_control_relay_with_socket_passing(stbt_control_relay_on_path):  # pylint: disable=unused-argument
    with NamedTemporaryFile(prefix="stbt-control-relay-test-") as tmpfile:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        s.listen(5)

        proc = subprocess.Popen(
            ["stbt-control-relay", "-vv", "file:" + tmpfile.name],
            preexec_fn=socket_passing_setup(s))
        with scoped_process(proc):
            testremote = uri_to_remote("lirc:%s:%i:stbt" % s.getsockname())

            testremote.press("KEY_UP")
            testremote.press("KEY_DOWN")
            expected = "KEY_UP\nKEY_DOWN\n"

            assert tmpfile.read() == expected
