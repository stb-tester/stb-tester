#!/usr/bin/python
"""
Allows using any of the stbt remote control backends remotely using the lirc
protocol.

Presents the same socket protocol as lircd but sending keypresses using any of
stbt's controls.  This allows for example controlling a roku over its HTTP
interface from some software that only speaks lirc.

Example usage:

    $ stbt control-relay file:example

Listens on `/var/run/lirc/lircd` for lirc clients.  Keypress sent will be
written to the file example.  So

    $ irsend SEND_ONCE stbt KEY_UP

Will write the text "KEY_UP" to the file `example`.

    $ stbt control-relay --socket=lircd.sock roku:192.168.1.13

Listens on lircd.sock and will forward keypresses to the roku at 192.168.1.13
using its HTTP protocol.  So

    $ irsend -d lircd.sock SEND_ONCE stbt KEY_OK

Will press KEY_OK on the roku device.
"""
import argparse
import os
import re
import signal
import socket
import sys

import _stbt.logging
from _stbt.control import uri_to_remote


def main(argv):
    parser = argparse.ArgumentParser(
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--socket", default="/var/run/lirc/lircd", help="""LIRC socket to read
        remote control presses from (defaults to %(default)s).""")
    parser.add_argument("output", help="""Remote control configuration to
        transmit on. Values are the same as stbt run's --control.""")
    _stbt.logging.argparser_add_verbose_argument(parser)
    args = parser.parse_args(argv[1:])

    signal.signal(signal.SIGTERM, lambda _signo, _stack_frame: sys.exit(0))

    if os.environ.get('LISTEN_FDS') == '1' and \
            os.environ.get('LISTEN_PID') == str(os.getpid()):
        s = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(args.socket)
        s.listen(5)

    control = uri_to_remote(args.output)

    while True:
        conn, _ = s.accept()
        f = conn.makefile('r', 0)
        while True:
            cmd = f.readline()
            if not cmd:
                break
            cmd = cmd.rstrip("\n")
            m = re.match(r"(?P<action>SEND_ONCE|SEND_START|SEND_STOP) "
                         r"(?P<ctrl>\S+) (?P<key>\S+)", cmd)
            if not m:
                debug("Invalid command: %s" % cmd)
                send_response(conn, cmd, success=False,
                              data="Invalid command: %s" % cmd)
                continue
            action = m.groupdict()["action"]
            key = m.groupdict()["key"]
            debug("Received %s %s" % (action, key))
            try:
                if action == "SEND_ONCE":
                    control.press(key)
                elif action == "SEND_START":
                    control.keydown(key)
                elif action == "SEND_STOP":
                    control.keyup(key)
            except Exception as e:  # pylint: disable=broad-except
                debug("Error pressing key %r: %r" % (key, e))
                send_response(conn, cmd, success=False, data=str(e))
                continue
            send_response(conn, cmd, success=True)


def send_response(sock, request, success, data=""):
    # See http://www.lirc.org/html/lircd.html
    message = "BEGIN\n{cmd}\n{status}\n".format(
        cmd=request,
        status="SUCCESS" if success else "ERROR")
    if data:
        data = data.split("\n")
        message += "DATA\n{length}\n{data}\n".format(
            length=len(data),
            data="\n".join(data))
    message += "END\n"

    try:
        sock.sendall(message)
    except Exception:  # pylint: disable=broad-except
        pass


def debug(s):
    _stbt.logging.debug("stbt-control-relay: %s" % s)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
