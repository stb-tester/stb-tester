#!/usr/bin/python

import glob
import os
import timeit

import stbt


def main():
    os.chdir(os.path.dirname(__file__))

    print "screenshot,reference,min,t1,t2,t3,t4,t5,t6,t7,t8,t9,t10"

    for fname in glob.glob("images/performance/*-frame.png"):
        tname = fname.replace("-frame.png", "-reference.png")
        f = stbt.load_image(fname)
        t = stbt.load_image(tname)
        # pylint:disable=cell-var-from-loop
        times = timeit.repeat(lambda: stbt.match(t, f), number=1, repeat=10)
        print "%s,%s,%f,%s" % (os.path.basename(fname),
                               os.path.basename(tname),
                               min(times),
                               ",".join("%f" % x for x in times))


if __name__ == "__main__":
    main()
