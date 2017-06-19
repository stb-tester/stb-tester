#!/usr/bin/python

import os
import sys
import time


try:
    mtime = os.stat('/tmp/stbt-start').st_mtime
except OSError:
    with open('/tmp/stbt-start', 'w') as f:
        mtime = os.fstat(f.fileno()).st_mtime
    sys.stderr.write("========== elapsed_print start time %i\n" % mtime)


def elapsed_print(*args):
    t = time.time()
    sys.stderr.write("+%0.02f %s\n" % (
        t - mtime, " ".join(str(x) for x in args)))


if __name__ == '__main__':
    elapsed_print(*sys.argv[1:])

