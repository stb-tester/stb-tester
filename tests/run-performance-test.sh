#!/bin/bash

# Tests stbt.detect_match against "stb-tester/tests/video.mpeg", which you
# must provide. It must be an H.264 MPEG-TS (e.g. a video captured with the
# Hauppauge HD PVR).

cd "$(dirname "$0")"


cat > script.$$ <<-EOF
	import stbt
	for m in stbt.detect_match("videotestsrc-redblue.png", timeout_secs=10):
	    print "%s %s %s" % (m.timestamp, m.match, m.position)
	EOF
trap "rm -f script.$$" EXIT

( time -p ../stbt-run \
    --source-pipeline \
      "filesrc location=video.mpeg ! mpegtsdemux ! video/x-h264 ! decodebin2" \
    --control none \
    script.$$ |
  wc -l
) 2>&1 |
awk '
  NR == 1 { frames = $1 }
  /real/  { print (frames/$2) " fps (" frames " frames in " $2 "s)" }'
