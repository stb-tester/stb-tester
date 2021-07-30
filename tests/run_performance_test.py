#!/usr/bin/python3

import glob
import os
import subprocess
import sys
import timeit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..")))
import stbt_core as stbt
sys.path.pop(0)


def main():
    os.chdir(os.path.dirname(__file__))

    # Disable cpu frequency scaling
    subprocess.check_call(r"""
        for cpu in /sys/devices/system/cpu/cpufreq/policy*; do
            echo $cpu
            cat $cpu/scaling_available_governors
            echo performance | sudo tee $cpu/scaling_governor
            freq=$(cat $cpu/cpuinfo_max_freq)
            echo $freq | sudo tee $cpu/scaling_min_freq
        done >&2
        """, shell=True)

    print("screenshot,reference,min,avg,max")

    for fname in glob.glob("images/performance/*-frame.png"):
        tname = fname.replace("-frame.png", "-reference.png")
        f = stbt.load_image(fname)
        t = stbt.load_image(tname)
        # pylint:disable=cell-var-from-loop
        times = timeit.repeat(lambda: stbt.match(t, f), number=1, repeat=100)
        print("%s,%s,%f,%f,%f" % (os.path.basename(fname),
                                  os.path.basename(tname),
                                  min(times),
                                  max(times),
                                  sum(times) / len(times)))


if __name__ == "__main__":
    main()
