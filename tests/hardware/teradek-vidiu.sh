#!/bin/sh

. $testdir/utils.sh

VIDIU_ADDRESS="vidiu-01188.local"
STREAM_NAME=steam

case $1 in
    start)
        sed "s,@SCRATCHDIR@,$scratchdir,g" \
            $testdir/hardware/crtmpserver.lua.in >"crtmpserver.lua"

        crtmpserver "crtmpserver.lua" &
        RTMPD_PID=$!

        # Wait for rtmp server to start up:
        started=false
        for i in $(seq 100); do
            netstat -ln --tcp | grep -q ':1935' && { started=true; break; }
            sleep 0.1
        done
        $started || fail "Failed to start crtmpserver"

        echo "$RTMPD_PID" >"$scratchdir/crtmpserver.pid"
        set_config global.source_pipeline \
            "rtmpsrc location=rtmp://localhost/live/$STREAM_NAME\ live=1 ! decodebin"
        ;;
    stop)
        kill $(<"$scratchdir/crtmpserver.pid")
        ;;
esac
