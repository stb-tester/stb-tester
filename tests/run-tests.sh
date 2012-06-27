#!/bin/sh

# Automated tests to test the stb-tester framework itself.
# See SETUP TIPS in ../README.rst for further information.

cd "$(dirname "$0")"
for tests in ./test-*.sh; do
    source $tests
done

run() {
    GST_DEBUG=
    scratchdir=$(mktemp -d -t stb-tester.XXX)
    printf "$1... "
    $1 > "$scratchdir/log" 2>&1
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

############################################################################

echo "Testing gstreamer + OpenCV installation:" &&
run test_gstreamer_core_elements &&
run test_gstreamer_can_find_templatematch &&
run test_gsttemplatematch_does_find_a_match &&
run test_gsttemplatematch_bgr_fix &&

echo "Testing stbt-run:" &&
run test_wait_for_match &&
run test_wait_for_match_no_match &&
run test_wait_for_match_changing_template &&

echo "All passed."
