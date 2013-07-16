import glob
import os
import time

import stbt


# Fail if this script is run more than once from the same $scratchdir
if len(glob.glob("../????-??-??_??.??.??*")) > 1:
    stbt.wait_for_match("videotestsrc-checkers-8.png", timeout_secs=1)

stbt.press("gamut")
stbt.wait_for_match("videotestsrc-gamut.png")

time.sleep(float(os.getenv("sleep", 0)))

stbt.press("smpte")
stbt.wait_for_motion()
