import os
import subprocess
from contextlib import contextmanager

from _stbt.control import uri_to_remote
from _stbt.core import wait_until
from _stbt.utils import named_temporary_directory


@contextmanager
def scoped_process(process):
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def srcdir(filename="", here=os.path.abspath(__file__)):
    return os.path.join(os.path.dirname(here), "..", filename)


def test_stbt_control_relay():
    with named_temporary_directory("stbt-control-relay-test.XXXXXX") as tmpdir:
        def t(filename):
            return os.path.join(tmpdir, filename)
        proc = subprocess.Popen(
            [srcdir("stbt_control_relay.py"),
             "--input=lircd:" + t("lircd.sock"),
             "file:" + t("one-file"), "file:" + t("another")])
        with scoped_process(proc):
            wait_until(lambda: (
                os.path.exists(t("lircd.sock")) or proc.poll() is not None))
            testremote = uri_to_remote("lirc:%s:stbt" % t("lircd.sock"))

            testremote.press("KEY_UP")
            testremote.press("KEY_DOWN")
            expected = "KEY_UP\nKEY_DOWN\n"

            def filecontains(filename, text):
                try:
                    with open(t(filename)) as f:
                        return text == f.read()
                except OSError:
                    return None

            wait_until(lambda: (
                filecontains("one-file", expected) and
                filecontains("another", expected)))
            assert open(t("one-file")).read() == expected
            assert open(t("another")).read() == expected
