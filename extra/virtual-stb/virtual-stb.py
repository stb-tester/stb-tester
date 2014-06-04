#!/usr/bin/python

import argparse
import contextlib
from enum import Enum
import os
import subprocess
import sys
import time

import jinja2

import stbt


def netstat():
    ns = subprocess.Popen(['netstat', '--unix', '-l', '-p'],
                          stdout=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    in_table = False
    cols = {}
    for line in ns.stdout:
        if not in_table:
            # Looking for header
            if 'Proto' in line:
                pidpos = line.index('PID/')
                pathpos = line.index('Path')
                in_table = True
        else:
            pid_prog = line[pidpos:pathpos].strip()
            if pid_prog == '-':
                pid, name = (None, None)
            else:
                pid, name = line[pidpos:pathpos].strip().split('/', 1)
            yield (pid, name, line[pathpos:].strip())


def xorg_pid(display_no):
    for pid, _, path in netstat():
        if path == '@/tmp/.X11-unix/X%i' % display_no:
            return int(pid)
    return None


class XStatus(Enum):
    SUCCESS=0
    FAILURE=1
    CONFLICT=2


def await_xorg_startup(xorg, display_no):
    while True:
        if xorg.poll() is not None:
            return XStatus.FAILURE

        p = xorg_pid(display_no)
        if p is not None:
            if p == xorg.pid:
                # Success
                return XStatus.SUCCESS
            else:
                # Some other process has this display name
                return XStatus.CONFLICT
        time.sleep(0.1)


@contextlib.contextmanager
def start_x(width, height):
    with open(os.path.dirname(__file__) + '/xorg.conf.jinja2') as f:
        xorg_conf_template = jinja2.Template(f.read())
    display_no = 10
    while display_no < 100:
        with stbt._named_temporary_directory(prefix='stbt-xorg-') as tmp, \
                open('/dev/null', 'r') as dev_null, \
                open('%s/xorg.output' % tmp, 'w') as xorg_output:

            with open('%s/xorg.conf' % tmp, 'w') as xorg_conf:
                xorg_conf.write(xorg_conf_template.render(
                    width=width, height=height))

            xorg = subprocess.Popen(
                ['Xorg', '-noreset', '+extension', 'GLX', '+extension', 'RANDR',
                 '+extension', 'RENDER', '-config', 'xorg.conf', '-logfile',
                 './xorg.log', ':%i' % display_no], stdin=dev_null,
                 stdout=xorg_output, stderr=subprocess.STDOUT, close_fds=True,
                 cwd=tmp)
            try:
                s = await_xorg_startup(xorg, display_no)
                if s is XStatus.SUCCESS:
                    wm = subprocess.Popen(
                        ['ratpoison', '-d', ':%i' % display_no], close_fds=True,
                        stdin=dev_null, stdout=xorg_output)
                    yield ":%i" % display_no
                    break
                elif s is XStatus.CONFLICT:
                    display_no += 1
                    continue
                elif s is XStatus.FAILURE:
                    raise RuntimeError("Failed to start X")
            finally:
                xorg.terminate()
                xorg.wait()


def main(argv):
    parser = argparse.ArgumentParser(
        description="Configure stb-tester to use a local program as "
                    "input/output")
    parser.add_argument('command', nargs=1)
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])

    with start_x(1280, 720) as display:
        stbt._set_config(
            'global', 'source_pipeline',
            'ximagesrc use-damage=false show-pointer=false '
            'display-name=%(x_display)s ! video/x-raw,framerate=24/1')
        stbt._set_config('global', 'control', 'x11:%(x_display)s')
        stbt._set_config('press', 'interpress_display_secs', '0.5')
        stbt._set_config('global', 'x_display', display)

        # TODO: Notify ready here

        os.environ['DISPLAY'] = display
        subprocess.check_call(args.command + args.args)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
