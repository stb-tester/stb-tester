import os
import socket
import subprocess
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from textwrap import dedent

import pytest

from _stbt.control import uri_to_control
from _stbt.wait import wait_until
from _stbt.utils import named_temporary_directory, scoped_process


# For py.test fixtures:
# pylint: disable=redefined-outer-name


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


@pytest.fixture(scope='session')
def installed_stbt_control_relay():
    with named_temporary_directory("stbt-control-relay-install.XXXXXX") as tmp:
        try:
            oldprefix = open(srcdir(".stbt-prefix"), encoding="utf-8").read()
        except IOError:
            oldprefix = None
        subprocess.check_call(
            ["make", "prefix=%s" % tmp, "install-stbt-control-relay"],
            cwd=srcdir())
        if oldprefix is not None:
            open(srcdir(".stbt-prefix"), "w", encoding="utf-8").write(oldprefix)
        else:
            os.unlink(srcdir(".stbt-prefix"))

        os.environ['PATH'] = "%s/bin:%s" % (tmp, os.environ['PATH'])
        yield "%s/bin/stbt-control-relay" % tmp


@pytest.fixture(scope='function')
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
            testcontrol = uri_to_control("lirc:%s:stbt-test" % t("lircd.sock"))

            testcontrol.press("KEY_LEFT")
            testcontrol.press("KEY_RIGHT")
            testcontrol.keydown("KEY_MENU")
            testcontrol.keyup("KEY_MENU")
            expected = dedent("""\
                KEY_LEFT
                KEY_RIGHT
                Holding KEY_MENU
                Released KEY_MENU
                """)

            assert expected == open(t("one-file"), encoding="utf-8").read()


def socket_passing_setup(socket):
    def preexec_fn():
        fd = socket.fileno()
        os.environ['LISTEN_FDS'] = '1'
        os.environ['LISTEN_PID'] = str(os.getpid())
        if fd != 3:
            os.dup2(fd, 3)
        os.set_inheritable(3, True)
        os.closerange(4, 100)

    return preexec_fn


def test_stbt_control_relay_with_socket_passing(stbt_control_relay_on_path):  # pylint: disable=unused-argument
    with NamedTemporaryFile(mode="w+",
                            prefix="stbt-control-relay-test-") as tmpfile:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        s.listen(5)

        proc = subprocess.Popen(  # pylint:disable=subprocess-popen-preexec-fn
            ["stbt-control-relay", "-vv", "file:" + tmpfile.name],
            preexec_fn=socket_passing_setup(s),
            close_fds=False)
        with scoped_process(proc):
            testcontrol = uri_to_control("lirc:%s:%i:stbt" % s.getsockname())

            testcontrol.press("KEY_UP")
            testcontrol.press("KEY_DOWN")
            expected = "KEY_UP\nKEY_DOWN\n"

            assert tmpfile.read() == expected
