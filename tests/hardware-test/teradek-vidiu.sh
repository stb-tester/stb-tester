#!/bin/sh

. $testdir/utils.sh

VIDIU_ADDRESS="vidiu-01188.local"
STREAM_NAME=steam

case $1 in
    start)
        sed "s,@SCRATCH_DIR@,$scratch_dir,g" \
            $testdir/hardware-test/crtmpserver.lua.in >"crtmpserver.lua"
        crtmpserver "crtmpserver.lua" &
        # Wait for rtmp server to start up:
        while ! netstat -ln --tcp | grep -q ':1935'; do
            sleep 0.1
        done
        RTMPD_PID=$!
        echo "$RTMPD_PID" >"$scratch_dir/crtmpserver.pid"
        set_config global.source_pipeline \
            "rtmpsrc location=rtmp://localhost/live/$STREAM_NAME\ live=1 ! decodebin"
        ;;
    stop)
        kill $(<"$scratch_dir/crtmpserver.pid")
        ;;
esac
