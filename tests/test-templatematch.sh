# Automated tests to verify your gstreamer + OpenCV installation.
# Run with ./run-tests.sh

# Test for a correct installation of gstreamer
test_gstreamer_core_elements() {
    timeout 5 gst-launch-0.10 videotestsrc num-buffers=10 ! ximagesink
}

# Test for our libgst-stb-tester.so gstreamer plugin.
#
test_gstreamer_can_find_templatematch() {
    gst-inspect-0.10 stbt-templatematch >/dev/null
}

# Test stbt-templatematch element reports all properties it should have
#
test_gsttemplatematch_has_all_element_properties() {
    cat > $scratchdir/test.py <<-EOF
	import gst
	gst_params = gst.element_factory_make('stbt-templatematch').props
	print dir(gst_params)
	assert hasattr(gst_params, 'matchMethod')
	assert hasattr(gst_params, 'matchThreshold')
	assert hasattr(gst_params, 'confirmMethod')
	assert hasattr(gst_params, 'erodePasses')
	assert hasattr(gst_params, 'confirmThreshold')
	assert hasattr(gst_params, 'template')
	assert hasattr(gst_params, 'debugDirectory')
	assert hasattr(gst_params, 'display')
	EOF
    python $scratchdir/test.py
}

test_gsttemplatematch_defaults_match_stbt_conf() {
    cat > $scratchdir/test.py <<-EOF
	import stbt
	import gst
	tol = 1e-6
	py_param = stbt.MatchParameters()
	c_param = gst.element_factory_make('stbt-templatematch').props
	assert c_param.matchMethod.value_nick == py_param.match_method
	assert abs(c_param.matchThreshold - py_param.match_threshold) < tol
	assert c_param.confirmMethod.value_nick == py_param.confirm_method
	assert c_param.erodePasses == py_param.erode_passes
	assert abs(c_param.confirmThreshold - py_param.confirm_threshold) < tol
	EOF
    PYTHONPATH=$testdir/.. python $scratchdir/test.py
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
# "gst-launch --messages" logs the bus messages; and the grep command will
# return success only if it finds a bus message from templatematch indicating a
# perfect match.
#
run_templatematch() {
    local template="$1"
    local log="$2"

    timeout 2 gst-launch-0.10 --messages \
        videotestsrc ! \
        ffmpegcolorspace ! \
        stbt-templatematch template="$template" matchMethod=1 ! \
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
