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
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import (ascii, chr, filter, hex, input, map, next, oct, open, pow,  # pylint:disable=redefined-builtin,unused-import,wildcard-import,wrong-import-order
                      range, round, super, zip)
import argparse
import logging
import os
import re
import signal
import socket
import sys

from _stbt.control import uri_to_control
from _stbt.utils import native_str, to_bytes


def main(argv):
    parser = argparse.ArgumentParser(
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--socket", default="/var/run/lirc/lircd", help="""LIRC socket to read
        remote control presses from (defaults to %(default)s).""")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("output", help="""Remote control configuration to
        transmit on. Values are the same as stbt run's --control.""")
    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO)

    signal.signal(signal.SIGTERM, lambda _signo, _stack_frame: sys.exit(0))

    if os.environ.get('LISTEN_FDS') == '1' and \
            os.environ.get('LISTEN_PID') == native_str(os.getpid()):
        s = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(args.socket)
        s.listen(5)

    control = uri_to_control(args.output)

    logging.info("stbt-control-relay started up with output '%s'", args.output)

    while True:
        conn, _ = s.accept()
        f = conn.makefile('rb', 0)
        while True:
            cmd = f.readline()
            if not cmd:
                break
            cmd = cmd.rstrip(b"\n")
            m = re.match(br"(?P<action>SEND_ONCE|SEND_START|SEND_STOP) "
                         br"(?P<ctrl>\S+) (?P<key>\S+)", cmd)
            if not m:
                logging.error("Invalid command: %s", cmd)
                send_response(conn, cmd, success=False,
                              data=b"Invalid command: %s" % cmd)
                continue
            action = m.group("action")
            key = m.group("key")
            logging.debug("Received %s %s", action, key)
            try:
                key = key.decode("utf-8")
                if action == b"SEND_ONCE":
                    control.press(key)
                elif action == b"SEND_START":
                    control.keydown(key)
                elif action == b"SEND_STOP":
                    control.keyup(key)
            except Exception as e:  # pylint: disable=broad-except
                logging.error("Error pressing key %r: %s", key, e,
                              exc_info=True)
                send_response(conn, cmd, success=False,
                              data=to_bytes(native_str(e)))
                continue
            send_response(conn, cmd, success=True)


def send_response(sock, request, success, data=b""):
    # See http://www.lirc.org/html/lircd.html
    message = b"BEGIN\n%s\n%s\n" % (
        request,
        b"SUCCESS" if success else b"ERROR")
    if data:
        data = data.split(b"\n")
        message += b"DATA\n%d\n%s\n" % (len(data), b"\n".join(data))
    message += b"END\n"

    try:
        sock.sendall(message)
    except Exception:  # pylint: disable=broad-except
        pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
