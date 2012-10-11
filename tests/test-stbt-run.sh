# Run with ./run-tests.sh

test_wait_for_match() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_match_no_match() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-bw-flipped.png", timeout_secs=1)
	EOF
    rm -f screenshot.png
    ! stbt-run -v "$scratchdir/test.py" &&
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
    stbt-run -v --control=none "$scratchdir/test.py"
}

test_wait_for_match_nonexistent_template() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("idontexist.png")
	EOF
    rm -f screenshot.png
    timeout 4 stbt-run -v "$scratchdir/test.py"
    local ret=$?
    echo "return code: $ret"
    [ $ret -ne $timedout -a $ret -ne 0 ]
}

test_detect_match_nonexistent_template() {
    cat > "$scratchdir/test.py" <<-EOF
	import sys
	m = detect_match("idontexist.png").next()
	sys.exit(0 if m.match else 1)
	EOF
    ! stbt-run -v "$scratchdir/test.py"
}

test_press_until_match() {
    # This doesn't test that press_until_match presses repeatedly, but at least
    # it tests that press_until_match doesn't blow up completely.
    cat > "$scratchdir/test.py" <<-EOF
	press_until_match("10", "videotestsrc-checkers-8.png")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_match_searches_in_script_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("in-script-dir.png", consecutive_matches=24)
	EOF
    cp videotestsrc-bw.png "$scratchdir/in-script-dir.png"
    stbt-run -v "$scratchdir/test.py"
}

test_press_until_match_searches_in_script_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	press_until_match("10", "in-script-dir.png")
	EOF
    cp videotestsrc-checkers-8.png "$scratchdir/in-script-dir.png"
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_searches_in_script_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	m = detect_match("in-script-dir.png").next()
	if not m.match:
	    raise Exception("'No match' when expecting match.")
	EOF
    cp videotestsrc-bw.png "$scratchdir/in-script-dir.png"
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_searches_in_library_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	import stbt_helpers
	stbt_helpers.find()
	EOF
    mkdir "$scratchdir/stbt_helpers"
    cat > "$scratchdir/stbt_helpers/__init__.py" <<-EOF
	import stbt
	def find():
	    m = stbt.detect_match("in-helpers-dir.png").next()
	    if not m.match:
	        raise Exception("'No match' when expecting match.")
	EOF
    cp videotestsrc-bw.png "$scratchdir/stbt_helpers/in-helpers-dir.png"
    PYTHONPATH="$scratchdir:$PYTHONPATH" stbt-run -v "$scratchdir/test.py"
}

test_detect_match_searches_in_caller_directory() {
    cat > "$scratchdir/test.py" <<-EOF
	import stbt_tests
	stbt_tests.find()
	EOF
    mkdir "$scratchdir/stbt_tests"
    cat > "$scratchdir/stbt_tests/__init__.py" <<-EOF
	import stbt_helpers
	def find():
	    stbt_helpers.find("in-caller-dir.png")
	EOF
    mkdir "$scratchdir/stbt_helpers"
    cat > "$scratchdir/stbt_helpers/__init__.py" <<-EOF
	import stbt
	def find(image):
	    m = stbt.detect_match(image).next()
	    if not m.match:
	        raise Exception("'No match' when expecting match.")
	EOF
    cp videotestsrc-bw.png "$scratchdir/stbt_tests/in-caller-dir.png"
    PYTHONPATH="$scratchdir:$PYTHONPATH" stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames=10)
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_no_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="videotestsrc-mask-no-video.png",
	        consecutive_frames=10, timeout_secs=1)
	EOF
    ! stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_nonexistent_mask() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="idontexist.png")
	press("OK")
	wait_for_motion(mask="idontexist.png")
	EOF
    timeout 4 stbt-run -v "$scratchdir/test.py"
    local ret=$?
    echo "return code: $ret"
    [ $ret -ne $timedout -a $ret -ne 0 ]
}

test_changing_input_video_with_the_test_control() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	press("10")  # checkers 8px
	wait_for_match("videotestsrc-checkers-8.png", consecutive_matches=24)
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_reports_match() {
    cat > "$scratchdir/test.py" <<-EOF
	# Should report a match
	for match_result in detect_match("videotestsrc-redblue.png"):
	    if match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("No match incorrectly reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_reports_match_position() {
    cat > "$scratchdir/test.py" <<-EOF
	for match_result in detect_match("videotestsrc-redblue.png"):
	    if match_result.position.x == 228 and match_result.position.y == 0:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrong match position reported, expected: (228,0),"
                            " got %s." % str(match_result.position))
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_reports_valid_timestamp() {
    cat > "$scratchdir/test.py" <<-EOF
	last_timestamp=None
	for match_result in detect_match("videotestsrc-redblue.png"):
	    if last_timestamp != None:
	        if match_result.timestamp - last_timestamp >= 0:
	            import sys
	            sys.exit(0)
	        else:
	            raise Exception("Invalid timestamps reported: %d - %d." % (
	                            last_timestamp, match_result.timestamp))
	    if match_result.timestamp == None:
	        raise Exception("Empty timestamp reported.")
	    last_timestamp = match_result.timestamp
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_reports_no_match() {
    cat > "$scratchdir/test.py" <<-EOF
	# Should not report a match
	for match_result in detect_match("videotestsrc-checkers-8.png"):
	    if not match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrong match reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_times_out() {
    cat > "$scratchdir/test.py" <<-EOF
	for match_result in detect_match("videotestsrc-redblue.png",
	                                 timeout_secs=1):
	    pass
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_times_out_during_yield() {
    cat > "$scratchdir/test.py" <<-EOF
	for match_result in detect_match("videotestsrc-redblue.png",
	                                 timeout_secs=1):
	    import time
	    time.sleep(2.0)
	EOF
    timeout 4 stbt-run -v "$scratchdir/test.py"
    local ret=$?
    echo "return code: $ret"
    [ $ret -ne $timedout -a $ret -eq 0 ]
}

test_detect_match_changing_template_is_not_racy() {
    # This test can seem a bit complicated, but the race occured even with:
    #   # Supposed to match and matches
    #   wait_for_match("videotestsrc-bw.png", timeout_secs=1)
    #   # Not supposed to match but matches intermittently
    #   wait_for_match("videotestsrc-bw-flipped.png", timeout_secs=1)
    cat > "$scratchdir/test.py" <<-EOF
	for match_result in detect_match("videotestsrc-bw.png", timeout_secs=1):
	    if not match_result.match:
	        raise Exception("Match not reported.")
	    # Leave time for another frame to be processed with this template
	    import time
	    time.sleep(1.0) # make sure the test fail (0.1s also works)
	    break
	for match_result in detect_match("videotestsrc-bw-flipped.png"):
	    # Not supposed to match
	    if not match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrongly reported a match: race condition.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_match_example_press_and_wait_for_match() {
    cat > "$scratchdir/test.py" <<-EOF
	key_sent = False
	for match_result in detect_match("videotestsrc-checkers-8.png"):
	    if not key_sent:
	        if match_result.match:
	            raise Exception("Wrong match reported.")
	        press("10")  # checkers 8px
	        key_sent = True
	    else:
	        if match_result.match:
	            import sys
	            sys.exit(0)
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_reports_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	# Should report motion
	for motion_result in detect_motion():
	    if motion_result.motion:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Motion not reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_reports_valid_timestamp() {
    cat > "$scratchdir/test.py" <<-EOF
	last_timestamp=None
	for motion_result in detect_motion():
	    if last_timestamp != None:
	        if motion_result.timestamp - last_timestamp >= 0:
	            import sys
	            sys.exit(0)
	        else:
	            raise Exception("Invalid timestamps reported: %d - %d." % (
	                            last_timestamp, motion_result.timestamp))
	    if motion_result.timestamp == None:
	        raise Exception("Empty timestamp reported.")
	    last_timestamp = motion_result.timestamp
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_reports_no_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	# Should not report motion
	for motion_result in detect_motion(mask="videotestsrc-mask-no-video.png"):
	    if not motion_result.motion:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Motion incorrectly reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_times_out() {
    cat > "$scratchdir/test.py" <<-EOF
	for motion_result in detect_motion(timeout_secs=1):
	    pass
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_times_out_during_yield() {
    cat > "$scratchdir/test.py" <<-EOF
	for motion_result in detect_motion(timeout_secs=1):
	    import time
	    time.sleep(2.0)
	EOF
    timeout 4 stbt-run -v "$scratchdir/test.py"
    local ret=$?
    echo "return code: $ret"
    [ $ret -ne $timedout -a $ret -eq 0 ]
}

test_detect_motion_changing_mask() {
    # Tests that we can change the mask given to motiondetect.
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="videotestsrc-mask-video.png")
	for motion_result in detect_motion(mask="videotestsrc-mask-no-video.png"):
	    if not motion_result.motion:
	        import sys
	        sys.exit(0)
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_changing_mask_is_not_racy() {
    cat > "$scratchdir/test.py" <<-EOF
	for motion_result in detect_motion(mask="videotestsrc-mask-video.png"):
	    if not motion_result.motion:
	        raise Exception("Motion not reported.")
	    # Leave time for another frame to be processed with this mask
	    import time
	    time.sleep(1.0) # make sure the test fail (0.1s also works)
	    break
	for motion_result in detect_motion(mask="videotestsrc-mask-no-video.png"):
	    # Not supposed to detect motion
	    if not motion_result.motion:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrongly reported motion: race condition.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_detect_motion_example_press_and_wait_for_no_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	key_sent = False
	for motion_result in detect_motion():
	    if not key_sent:
	        if not motion_result.motion:
	            raise Exception("Motion not reported.")
	        press("10")  # checkers 8px
	        key_sent = True
	    else:
	        if not motion_result.motion:
	            import sys
	            sys.exit(0)
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_precondition_script() {
    cat > "$scratchdir/test.py" <<-EOF
	from preconditions import *
	checkers_via_gamut()
	wait_for_match("videotestsrc-checkers-8.png", consecutive_matches=24)
	EOF
    PYTHONPATH="$testdir:$PYTHONPATH" stbt-run -v "$scratchdir/test.py"
}
