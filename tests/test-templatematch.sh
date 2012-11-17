# Automated tests to verify your gstreamer + OpenCV installation.
# Run with ./run-tests.sh

# Test for a correct installation of gstreamer
test_gstreamer_core_elements() {
    timeout 2 gst-launch videotestsrc ! ximagesink
    [ $? -eq $timedout ]
}

# Test for our libgst-stb-tester.so gstreamer plugin.
#
test_gstreamer_can_find_templatematch() {
    gst-inspect stbt-templatematch >/dev/null
}

# You should see a red rectangle (drawn by templatematch) around the black and
# white rectangles on the right of the test video.
#
test_gsttemplatematch_does_find_a_match() {
    run_templatematch videotestsrc-bw.png "$scratchdir/gst-launch.log"
}

# Test that the gstreamer templatematch element includes the fixes from
# https://bugzilla.gnome.org/show_bug.cgi?id=678485
#
# You should see a red rectangle (drawn by templatematch) around the red and
# blue rectangles on the right of the test video.
#
test_gsttemplatematch_bgr_fix() {
    run_templatematch videotestsrc-redblue.png "$scratchdir/gst-launch.log"
}

# The templatematch element sends a bus message for each frame it processes;
# with GST_DEBUG=4 we can see the bus messages; and the grep command will
# return success only if it finds a bus message from templatematch indicating a
# perfect match.
#
run_templatematch() {
    local template="$1"
    local log="$2"

    timeout 2 gst-launch --messages \
        videotestsrc ! \
        ffmpegcolorspace ! \
        stbt-templatematch template="$template" method=1 ! \
        ffmpegcolorspace ! \
        ximagesink \
    > "$log" 2>&1

    if [ $? -ne $timedout ]; then
        echo "Failed to launch gstreamer pipeline; see '$log'"
        return 1
    fi

    if ! grep 'template_match.*match=(boolean)true' "$log"; then
        echo "templatematch didn't find '$template'."
        grep 'template_match.*match=' "$log"  # debug for $scratchdir/log
        return 1
    fi
}
