#!/bin/sh

# Automated tests to test the stb-tester framework itself.
# See SETUP TIPS in ../README.rst for further information.

cd "$(dirname "$0")"
source ./test-*.sh

test_gstreamer() {
    echo "Testing gstreamer + OpenCV installation:"
    run test_gstreamer_core_elements &&
    run test_gstreamer_can_find_templatematch &&
    run test_gsttemplatematch_does_find_a_match &&
    run test_gsttemplatematch_bgr_fix
}

test_stbt_run() {
    echo "Testing stbt run:"
    run stbt run --source-pipeline=videotestsrc test-wait_for_match.py
}

run() {
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    printf "$*... "
    $* > "$scratchdir/log" 2>&1
    if [ $? -eq 0 ]; then
        echo "OK"
        rm -f "$scratchdir/log" "$scratchdir/gst-launch.log"
        rmdir "$scratchdir"
        true
    else
        echo "FAIL"
        echo "See '$scratchdir/log'"
        false
    fi
}

# Portable timeout command. Usage: timeout <secs> <command> [<args>...]
timeout() { perl -e 'alarm shift @ARGV; exec @ARGV' "$@"; }
timedout=142

test_gstreamer &&
test_stbt_run
