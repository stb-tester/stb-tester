# Run with ./run-tests.sh

test_wait_for_match() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	EOF
    stbt-run "$scratchdir/test.py"
}

test_wait_for_match_no_match() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-bw-flipped.png", timeout_secs=1)
	EOF
    rm -f screenshot.png
    ! stbt-run "$scratchdir/test.py" &&
    [ -f screenshot.png ]
}

test_wait_for_match_changing_template() {
    # Tests that we can change the image given to templatematch.
    # Also tests the remote-control infrastructure by using the null control.
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	press("MENU")
	wait_for_match("videotestsrc-bw.png", consecutive_matches=24)
	press("OK")
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	EOF
    stbt-run --control=none "$scratchdir/test.py"
}

test_wait_for_match_nonexistent_template() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("idontexist.png")
	EOF
    rm -f screenshot.png
    timeout 2 stbt-run "$scratchdir/test.py"
    local ret=$?
    [ $ret -ne $timedout -a $ret -ne 0 ]
}

test_press_until_match() {
    # This doesn't test that press_until_match presses repeatedly, but at least
    # it tests that press_until_match doesn't blow up completely.
    cat > "$scratchdir/test.py" <<-EOF
	press_until_match("10", "videotestsrc-checkers-8.png")
	EOF
    stbt-run "$scratchdir/test.py"
}

test_wait_for_match_searches_in_script_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("in-script-dir.png", consecutive_matches=24)
	EOF
    cp videotestsrc-bw.png "$scratchdir/in-script-dir.png"
    stbt-run "$scratchdir/test.py"
}

test_press_until_match_searches_in_script_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	press_until_match("10", "in-script-dir.png")
	EOF
    cp videotestsrc-checkers-8.png "$scratchdir/in-script-dir.png"
    stbt-run "$scratchdir/test.py"
}

test_wait_for_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames=10)
	EOF
    stbt-run "$scratchdir/test.py"
}

test_wait_for_motion_no_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="videotestsrc-mask-no-video.png",
	        consecutive_frames=10, timeout_secs=1)
	EOF
    ! stbt-run "$scratchdir/test.py"
}

test_changing_input_video_with_the_test_control() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	press("10")  # checkers 8px
	wait_for_match("videotestsrc-checkers-8.png", consecutive_matches=24)
	EOF
    stbt-run "$scratchdir/test.py"
}

test_precondition_script() {
    cat > "$scratchdir/test.py" <<-EOF
	from preconditions import *
	checkers_via_gamut()
	wait_for_match("videotestsrc-checkers-8.png", consecutive_matches=24)
	EOF
    PYTHONPATH="$testdir:$PYTHONPATH" stbt-run "$scratchdir/test.py"
}
