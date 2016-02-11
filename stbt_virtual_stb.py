#!/usr/bin/env python
"""
stbt virtual-stb enables stb-tester to test set-top box software without
hardware.  This can be useful as a first stage in a continuous integration
pipeline as testing can be scaled up with computing resources rather than
relying on fixed hardware.

EXAMPLE USAGE
-------------

Run some tests against youtube HTML5 TV edition:

    # With this your existing stbt configuration won't be overridden:
    export STBT_CONFIG_FILE=/tmp/stbt.conf

    # This will launch chromium-browser and set stbt to read video from and send
    # keypresses to chromium by modifying $STBT_CONFIG_FILE:
    stbt virtual-stb run --background chromium --app=http://youtube.com/tv

    # Run a test against the YouTube UI set up before:
    stbt run tests/youtube.py::test_playing_popular_content

    # Tear down the chromium and the virtual stb and remove the configuration:
    stbt virtual-stb stop
"""

import argparse
import errno
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

from _stbt.config import get_config, set_config
from _stbt.x11 import x_server


@contextmanager
def virtual_stb(command, x_keymap=None, verbose=False):
    with x_server(1280, 720, verbose=verbose) as display:
        subprocess.Popen(
            ['ratpoison', '-d', display], close_fds=True,
            stdin=open('/dev/null', 'r'), stdout=open('/dev/null', 'w'),
            stderr=subprocess.STDOUT)

        os.environ['DISPLAY'] = display
        child = subprocess.Popen(command, shell=True)

        try:
            config = {
                "control": "x11:%(x_display)s,%(x_keymap)s",
                "x_keymap": x_keymap if x_keymap is not None else "",
                "source_pipeline": (
                    'ximagesrc use-damage=false remote=true show-pointer=false '
                    'display-name=%(x_display)s ! video/x-raw,framerate=24/1'),
                "x_display": display,
                "vstb_child_pid": str(child.pid),
                "vstb_pid": str(os.getpid()),
            }
            yield (child, config)
        finally:
            if child.poll() is None:
                child.terminate()


def main(argv):
    parser = argparse.ArgumentParser(
        description="Configure stb-tester to use a local program as "
                    "input/output", epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='subcommand')
    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('-b', '--background', action="store_true",
                            help="Run virtual-stb in background")
    run_parser.add_argument('-v', '--verbose', action="store_true",
                            help="Print xorg logs to console")
    run_parser.add_argument(
        '--x-keymap', help="Filename of file mapping key names to X keysyms")
    run_parser.add_argument('command', nargs=1)
    run_parser.add_argument('args', nargs=argparse.REMAINDER)

    stop_parser = subparsers.add_parser('stop')
    stop_parser.add_argument('-f', '--force', action="store_true",
                             help="Ignore errors")

    args = parser.parse_args(argv[1:])

    if args.subcommand == 'run':
        # Do run our `finally` teardown blocks on SIGTERM
        signal.signal(signal.SIGTERM, lambda _signo, _frame: sys.exit(0))

        write_end = None
        if args.background:
            read_end, write_end = multiprocessing.Pipe(duplex=False)
            pid = os.fork()
            if pid:
                # Parent - wait for child to be ready
                write_end.close()
                read_end.recv()
                return 0
            else:
                # Child
                read_end.close()

        with virtual_stb(args.command + args.args, verbose=args.verbose,
                         x_keymap=args.x_keymap) as (child, config):
            for k, v in config.items():
                set_config('global', k, v)

            try:
                if write_end is not None:
                    write_end.send(True)
                    write_end.close()
                child.wait()
            finally:
                for k in config.keys():
                    set_config('global', k, None)
    elif args.subcommand == 'stop':
        try:
            pid = get_config('global', 'vstb_pid', None)
            set_config('global', 'vstb_pid', None)
            os.kill(int(pid), signal.SIGTERM)
            while True:
                try:
                    os.kill(int(pid), 0)
                    time.sleep(0.1)
                except OSError as e:
                    if e.errno == errno.ESRCH:
                        return 0
                    else:
                        raise
        except Exception:  # pylint: disable=broad-except
            if not args.force:
                raise

if __name__ == '__main__':
    sys.exit(main(sys.argv))
