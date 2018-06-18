#!/bin/bash

# Tests stbt.detect_match against "stb-tester/tests/video.mpeg", which you
# must provide. It must be an H.264 MPEG-TS (e.g. a video captured with the
# Hauppauge HD PVR).

cd "$(dirname "$0")"


cat > script.$$ <<-EOF
	import datetime, stbt
	frames = 0
	stbt.frames().next()  # Don't count pipeline startup time
	start = datetime.datetime.now()
	for m in stbt.detect_match("videotestsrc-redblue.png", timeout_secs=10):
	    frames += 1
	    print "%.3f %s %s" % (m.time, bool(m), m.position)
	    # if not m:
	    #     break
	duration = (datetime.datetime.now() - start).total_seconds()
	print "%.2f fps (%d frames in %.2fs)" % (
	    frames / duration, frames, duration)
	EOF
trap "rm -f script.$$" EXIT

../stbt-run \
    --source-pipeline "filesrc location=video.mpeg" \
    --control none \
    script.$$
