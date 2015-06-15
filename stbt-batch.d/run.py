#!/usr/bin/env python

# Copyright 2015 stb-tester.com Ltd.
# License: LGPL v2.1 or (at your option) any later version (see
# https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).


import argparse
import os
import signal
import subprocess
import sys
from distutils.spawn import find_executable


def main(argv):
    runner = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(usage=(
        "\n  stbt batch run [options] test.py [test.py ...]"
        "\n  stbt batch run [options] test.py arg [arg ...] -- "
        "test.py arg [arg ...] [-- ...])"))
    parser.add_argument(
        '-1', '--run-once', action="store_true", help=(
            'Run once. The default behaviour is to run the test repeatedly as '
            'long as it passes.'))
    parser.add_argument(
        '-k', '--keep-going', action="count", help=(
            'Continue running after failures.  Provide this argument once to '
            'continue running after "uninteresting" failures, and twice to '
            'continue running after any failure (except those that would '
            'prevent any further test from passing).'))
    parser.add_argument(
        '-d', '--debug', action="store_true", help=(
            'Enable "stbt-debug" dump of intermediate images.'))
    parser.add_argument(
        '-v', '--verbose', action="count", default=0, help=(
            'Verbose. Provide this argument once to print stbt standard '
            'output. Provide this argument twice to also print stbt stderr '
            'output.'))
    parser.add_argument(
        '-o', '--output', default=os.curdir, help=(
            'Output directory to save the report and test-run logs under '
            '(defaults to the current directory).'))
    parser.add_argument(
        '-t', '--tag', help=(
            'Tag to add to test run directory names (useful to differentiate '
            'directories when you intend to merge test results from multiple '
            'machines).'))
    parser.add_argument('test_name', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])

    if args.tag is not None:
        tag = '-' + args.tag
    else:
        tag = ""

    os.environ['PYTHONUNBUFFERED'] = 'x'

    term_count = [0]

    def on_term(_signo, _frame):
        term_count[0] += 1
        if term_count[0] == 1:
            sys.stderr.write(
                "\nReceived interrupt; waiting for current test to complete.\n")
        else:
            sys.stderr.write("Received interrupt; exiting.\n")
            sys.exit(1)

    signal.signal(signal.SIGINT, on_term)
    signal.signal(signal.SIGTERM, on_term)

    stop = [False]
    failure_count = 0
    last_exit_status = 0

    if not find_executable('ts'):
        sys.stderr.write(
            "No 'ts' command found; please install 'moreutils' package\n")
        return 1

    tests = parse_test_args(args.test_name)

    DEVNULL_R = open('/dev/null', 'r')
    run_count = 0
    while not stop[0] and term_count[0] == 0:
        for test in tests:
            if stop[0] or term_count[0] > 0:
                break
            run_count += 1
            subenv = dict(os.environ)
            subenv['tag'] = tag
            subenv['v'] = '-vv' if args.debug else '-v'
            subenv['verbose'] = str(args.verbose)
            subenv['outputdir'] = args.output
            child = None
            try:
                child = subprocess.Popen(
                    ["%s/run-one" % runner] + test, stdin=DEVNULL_R, env=subenv,
                    preexec_fn=lambda: os.setpgid(0, 0))
                last_exit_status = child.wait()
            except SystemExit:
                if child:
                    os.kill(-child.pid, signal.SIGTERM)
                    child.wait()
                raise

            if last_exit_status != 0:
                failure_count += 1
            if os.path.exists(
                    "%s/latest%s/unrecoverable-error" % (args.output, tag)):
                stop[0] = True

            if last_exit_status == 0:
                continue
            elif last_exit_status >= 2 and args.keep_going > 0:
                # "Uninteresting" failures due to the test infrastructure
                continue
            elif args.keep_going >= 2:
                continue
            else:
                stop[0] = True

        if args.run_once:
            break

    if run_count == 1:
        # If we only run a single test a single time propagate the result
        # through
        return last_exit_status
    elif failure_count == 0:
        return 0
    else:
        return 1


def listsplit(l, v):
    """
    A bit like str.split, but for lists

    >>> listsplit(['test 1', '--', 'test 2', 'arg1', '--', 'test3'], '--')
    [['test 1'], ['test 2', 'arg1'], ['test3']]
    """
    out = []
    sublist = []
    for x in l:
        if x == v:
            if sublist:
                out.append(sublist)
            sublist = []
        else:
            sublist.append(x)
    if sublist:
        out.append(sublist)
    return out


def parse_test_args(args):
    """
    >>> parse_test_args(['test 1.py', 'test2.py', 'test3.py'])
    [['test 1.py'], ['test2.py'], ['test3.py']]
    >>> parse_test_args(['test1.py', 'test2.py'])
    [['test1.py'], ['test2.py']]
    >>> parse_test_args(['test1.py', '--'])
    [['test1.py']]
    >>> parse_test_args(['test1.py', '--', 'test2.py'])
    [['test1.py'], ['test2.py']]
    >>> parse_test_args(['test1.py', '--', 'test2.py', '--'])
    [['test1.py'], ['test2.py']]
    >>> parse_test_args(['test1.py', 'test2.py'])
    [['test1.py'], ['test2.py']]
    >>> parse_test_args(
    ...     ['test1.py', 'arg1', 'arg2', '--', 'test2.py', 'arg', '--',
    ...      'test3.py'])
    [['test1.py', 'arg1', 'arg2'], ['test2.py', 'arg'], ['test3.py']]
    """
    if '--' in args:
        return listsplit(args, '--')
    else:
        return [[x] for x in args]

if __name__ == '__main__':
    sys.exit(main(sys.argv))
