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

    $ stbt control-relay --input=lircd:lircd.sock \\
          roku:192.168.1.13 samsung:192.168.1.14

Listens on lircd.sock and will forward keypresses to the roku at 192.168.1.13
using its HTTP protocol and to the Samsung TV at 192.168.1.14 using its TCP
protocol.  So

    $ irsend -d lircd.sock SEND_ONCE stbt KEY_OK

Will press KEY_OK on both the Samsung and the roku devices simultaneously.
"""
import argparse
import signal
import sys

from _stbt.control import MultiRemote, uri_to_remote, uri_to_remote_recorder


def main(argv):
    parser = argparse.ArgumentParser(
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="lircd")
    parser.add_argument("output", nargs="*")
    args = parser.parse_args(argv[1:])

    signal.signal(signal.SIGTERM, lambda _signo, _stack_frame: sys.exit(0))

    r = MultiRemote(uri_to_remote(x) for x in args.output)
    listener = uri_to_remote_recorder(args.input)
    for key in listener:
        sys.stderr.write("Received %s\n" % key)
        try:
            r.press(key)
        except Exception as e:  # pylint: disable=broad-except
            sys.stderr.write("Error pressing key %r: %s\n" % (key, e))

if __name__ == "__main__":
    sys.exit(main(sys.argv))
