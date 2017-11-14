import datetime
import json
import os
import socket
import sys
from cStringIO import StringIO


class StateSender(object):
    """
    A test run is in a particular state.  This state includes what test is
    currently executing, what line is currently executing, etc.  This state
    needs to be communicated live to the UI and should be useful during test
    replay when investigating what has gone wrong.

    The data structure is like:

        {
            "test_run": {
                "current_line": {
                    "file": "tests/my_file.py",
                    "line": 123,
                },
                "test_case": {
                    "name": "tests/my_file.py::test_that_this_rocks",
                    "file": "tests/my_file.py",
                    "function": "test_that_this_rocks,
                    "line": 87
                }
            }
        }

    Conceptually the data-structure lives in the test-pack.  It is ephermal and
    only exists while the test job is executing.  Changes to this data structure
    are serialised and sent over a socket to the UI so the current state of the
    system can be displayed.  The serialisation includes timestamps such that
    the state of the system can be inspected and replayed as part of the test
    result.

    The change serialisation format is \\r\\n seperated JSON dictionaries.
    Here's an example entry pretty printed for clarity's sake (in reality it
    would be on a single line):

        {
            "state_change": {
                "time": "2014-11-28T20:55:26.092343Z",
                "changes": {
                    "test_run.current_line": {
                        "file": "tests/my_file.py",
                        "line": 654
                    }
                }
            }
        }

    This record indicates that the current line changed to line 654 of file
    "tests/my_file.py" at 20:55:26.0992343 UTC on 2014-11-28.  Notes:

    * The root object has a single key "state_change".  This allows extensions
      in the future for other types of messages to be sent over the same
      protocol.

    * The state_change message has two keys:

        * "time" which is the time of the change as a ISO8601 formatted string
          e.g `"2014-11-28T20:55:26.092343Z"`.

        * "changes" is a dictionary of changes made to the state of the system.
          The keys identify the value that is changing, and the values are the
          new value of the respective key.  The key is dot seperated strings
          identifying the subtree of the heirarical data structure that should
          be replaced.  e.g:

              "test_run.current_line": {"cow": "moo"}

          means:

              date["test_run"]["current_line"] = {"cow": "moo"}

          The fact that multiple values may be replaced in one message allows
          atomic changes to happen to the hierarchy.
    """
    def __init__(self, file_):
        self._file = file_

    def __enter__(self):
        pass

    def __exit__(self, _, _1, _2):
        self.close()

    def set(self, items, time=None):
        """
        >>> sw = StateSender(StringIO())
        >>> sw.set({"animals.noises": {"cow": "moo"}})
        """
        if time is None:
            time = datetime.datetime.now()
        message = {
            "state_change": {
                "time": time.isoformat(),
                "changes": items
            }
        }
        self._file.write(json.dumps(message, sort_keys=True) + '\r\n')

    def close(self):
        self._file.close()
        self._file = None

    def log_test_starting(self, func):
        self.set({"test_run": {
            "current_line": {},
            "test_case": {
                "name": func.script,
                "file": func.filename,
                "function": func.funcname,
                "line": func.line
            }}})

    def log_test_ended(self):
        self.set({"test_run": {}})

    def log_current_line(self, file_, line):
        self.set({"test_run.current_line": {"file": file_, "line": line}})


def test_state_changes():
    f = StringIO()
    sw = StateSender(f)
    sw.set({"test_run.line_number": 23},
           time=datetime.datetime(2014, 3, 4, 12, 45, 12))
    assert f.getvalue() == (
        '{"state_change": {"changes": {"test_run.line_number": 23}, '
        '"time": "2014-03-04T12:45:12"}}\r\n')


class _SocketAndFileWriter(object):
    def __init__(self, socket_, file_):
        self.file = file_
        self.socket = socket_

    def write(self, data):
        self.file.write(data)
        self.socket.sendall(data)

    def close(self):
        self.file.close()
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()


class _NullFile(object):
    def write(self, data):
        pass

    def close(self):
        pass


def new_state_sender(filename=None):
    try:
        from lzma import LZMAFile
    except ImportError:
        from backports.lzma import LZMAFile  # pylint:disable=E0611,F0401

    socket_ = None
    if filename is not None:
        fsfile_ = LZMAFile(filename, 'wb')
    else:
        fsfile_ = _NullFile()
    file_ = None
    try:
        socket_ = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_.connect(os.environ['STBT_TRACING_SOCKET'])
        file_ = _SocketAndFileWriter(socket_, fsfile_)
    except (KeyError, socket.error):
        file_ = fsfile_  # pylint:disable=redefined-variable-type
    return StateSender(file_)


def _set_heir(data, key, value):
    assert len(key) > 0
    if len(key) == 1:
        data[key[0]] = value
    else:
        _set_heir(data[key[0]], key[1:], value)


class StateReceiver(object):
    def __init__(self, state=None):
        if state is None:
            state = {}
        self.state = state
        self.olddata = ""

    def write(self, data):
        olddata, self.olddata = self.olddata, ""
        buf = StringIO(olddata + data)

        for line in buf:
            if not line.endswith('\n'):
                # EOF (for now) indicating incomplete line
                self.olddata = line
                return

            try:
                (msg_type, value), = json.loads(line).items()
                if msg_type != 'state_change':
                    return

                for k, v in sorted(value['changes'].items(),
                                   key=lambda x: len(x[0])):
                    _set_heir(self.state, k.split('.'), v)
            except StandardError as e:
                sys.stderr.write(
                    "Error processing state change: %s" % str(e))


def test_statereceiver():
    data = {}
    sr = StateReceiver(data)
    sr.write(
        '{"state_change": {"changes": {"test": 5, '
        '"test2": {"cat": "miaw"}}}}\r\n')
    assert data == {"test": 5, "test2": {"cat": "miaw"}}
    sr.write(
        '{"state_change": {"changes": {"test": 8, '
        '"test3": {"dog": "woof"}}}}\r\n')
    assert data == {"test": 8, "test2": {"cat": "miaw"},
                    "test3": {"dog": "woof"}}

    # Incomplete write: no change:
    sr.write('{"state_change": {"changes": {"te')
    assert data == {"test": 8, "test2": {"cat": "miaw"},
                    "test3": {"dog": "woof"}}

    # and finish that write:
    sr.write('st": 12, "test3": {"dog": "baa"}}}}\r\n')
    assert data == {"test": 12, "test2": {"cat": "miaw"},
                    "test3": {"dog": "baa"}}


def test_that_statesender_is_symmetrical_with_statereceiver():
    out = {}
    sr = StateReceiver(out)
    ss = StateSender(sr)

    ss.set({"names": ["Arnold", "Cat", "Dave", "Kryten"]})
    assert out['names'] == ["Arnold", "Cat", "Dave", "Kryten"]
