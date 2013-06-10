# Run with ./run-tests.sh

test_wait_for_motion_int() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames=10)
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_str() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames='10/10')
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_no_motion_int() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames=10, timeout_secs=1)
	EOF
    ! stbt-run -v --source-pipeline="videotestsrc ! imagefreeze" \
        "$scratchdir/test.py"
}

test_wait_for_motion_no_motion_str() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames='10/10', timeout_secs=1)
	EOF
    ! stbt-run -v --source-pipeline="videotestsrc ! imagefreeze" \
        "$scratchdir/test.py"
}

test_wait_for_motion_half_motion_str_2of4() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames='2/4', timeout_secs=1)
	EOF
    stbt-run -v --source-pipeline="videotestsrc is-live=true ! \
        video/x-raw-yuv,framerate=12/1 ! videorate force-fps=25/1 ! \
        ffmpegcolorspace" "$scratchdir/test.py"

}

test_wait_for_motion_half_motion_str_2of3() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames='2/3', timeout_secs=1)
	EOF
    stbt-run -v --source-pipeline="videotestsrc is-live=true ! \
        video/x-raw-yuv,framerate=12/1 ! videorate force-fps=25/1 ! \
        ffmpegcolorspace" "$scratchdir/test.py"
}

test_wait_for_motion_half_motion_str_3of4() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames='3/4', timeout_secs=1)
	EOF
    ! stbt-run -v --source-pipeline="videotestsrc is-live=true ! \
        video/x-raw-yuv,framerate=12/1 ! videorate force-fps=25/1 ! \
        ffmpegcolorspace" "$scratchdir/test.py"
}

test_wait_for_motion_half_motion_int() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(consecutive_frames=2, timeout_secs=1)
	EOF
    ! stbt-run -v --source-pipeline="videotestsrc is-live=true ! \
        video/x-raw-yuv,framerate=12/1 ! videorate force-fps=25/1 ! \
        ffmpegcolorspace" "$scratchdir/test.py"
}

test_wait_for_motion_with_mask_reports_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="videotestsrc-mask-video.png")
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_with_mask_does_not_report_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(mask="videotestsrc-mask-no-video.png", timeout_secs=1)
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

test_wait_for_motion_with_high_noisethreshold_reports_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(noise_threshold=1.0)
	EOF
    stbt-run -v "$scratchdir/test.py"
}

test_wait_for_motion_with_low_noisethreshold_does_not_report_motion() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(noise_threshold=0.0, timeout_secs=1)
	EOF
    ! stbt-run -v "$scratchdir/test.py"
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

test_detect_motion_with_debug_output_does_not_segfault_without_mask() {
    cat > "$scratchdir/test.py" <<-EOF
	wait_for_motion(timeout_secs=1)
	EOF
    stbt-run -vv "$scratchdir/test.py"  # creates stbt-debug

    if [ $? -eq 0 ] && [ -d "stbt-debug" ] && [ "$leave_scratch_dir" != "true" ]; then
        rm -rf "stbt-debug"
    fi
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
