# Run with ./run-tests.sh

test_wait_for_match() {
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png", consecutive_matches=2)
	EOF
    stbt-run -v test.py
}

test_wait_for_match_no_match() {
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=1)
	EOF
    ! stbt-run -v test.py &&
    [ -f screenshot.png ]
}

test_wait_for_match_changing_template() {
    # Tests that we can change the image given to templatematch.
    # Also tests the remote-control infrastructure by using the null control.
    cat > test.py <<-EOF
	wait_for_match("$testdir/videotestsrc-redblue.png")
	press("MENU")
	wait_for_match("$testdir/videotestsrc-bw.png")
	press("OK")
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png")
	EOF
    stbt-run -v --control=none test.py
}

test_wait_for_match_nonexistent_template() {
    cat > test.py <<-EOF
	wait_for_match("idontexist.png")
	EOF
    ! stbt-run -v test.py
}

test_wait_for_match_noise_threshold_raises_warning() {
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png", noise_threshold=0.2)
	EOF
    stbt-run -v test.py 2>&1 | grep 'DeprecationWarning'
}

test_wait_for_match_match_method_param_affects_first_pass() {
    # This works on the fact that match_method="ccorr-normed" registers a
    # first_pass_result greater than 0.80 which is then falsely confirmed as
    # a match, whereas match_method="sqdiff-normed" does not produce a
    # first_pass_result above 0.80 and so the match fails.
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue-flipped.png",
	    match_parameters=MatchParameters(
	        match_method="ccorr-normed", confirm_method="none"),
	    timeout_secs=1)
	EOF
    stbt-run -v test.py || return

    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue-flipped.png",
	    match_parameters=MatchParameters(
	        match_method="sqdiff-normed", confirm_method="none"),
	    timeout_secs=1)
	EOF
    ! stbt-run -v test.py
}

test_wait_for_match_match_threshold_param_affects_match() {
    # Confirm_method="none" means that if anything passes the first pass of
    # templatematching, it is considered a positive result. Using this, by
    # using 2 detect_matches with match_thresholds either side of the
    # first_pass_result of this match, we can get one to pass and the other
    # to fail.
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-checkers-8.png", timeout_secs=1,
	    match_parameters=MatchParameters(
	        match_threshold=0.8, confirm_method="none"))
	EOF
    ! stbt-run -v test.py || return

    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-checkers-8.png", timeout_secs=1,
	    match_parameters=MatchParameters(
	        match_threshold=0.2, confirm_method="none"))
	EOF
    stbt-run -v test.py
}

test_wait_for_match_confirm_method_none_matches_anything_with_match_threshold_zero() {
    # With match_threshold=0, the first pass is meaningless, and with
    # confirm_method="none", any image with match any source.
    # (In use, this scenario is completely useless).
    cat > test.py <<-EOF
	for img in ['circle-big.png', 'videotestsrc-redblue-flipped.png',
	            'videotestsrc-checkers-8.png', 'videotestsrc-gamut.png']:
	    wait_for_match("$testdir/" + img, match_parameters=MatchParameters(
	        match_threshold=0, confirm_method="none"))
	EOF
    stbt-run -v test.py
}

test_wait_for_match_confirm_methods_produce_different_results() {
    local source_pipeline="filesrc location=$testdir/known-fail-source.png ! \
        decodebin2 ! imagefreeze ! ffmpegcolorspace"

    # Expect correct nomatch.
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/known-fail-template.png",
	    match_parameters=MatchParameters(confirm_method="normed-absdiff"))
	EOF
    ! stbt-run -v --source-pipeline="$source_pipeline" --control=None test.py \
        || return

    # Expect false match.
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/known-fail-template.png",
	    match_parameters=MatchParameters(confirm_method="absdiff"))
	EOF
    stbt-run -v --source-pipeline="$source_pipeline" --control=None test.py
}

test_wait_for_match_erode_passes_affects_match() {
    # This test demonstrates that changing the number of erodePasses
    # can cause incongruent images to match falsely.
    local source_pipeline="filesrc location=$testdir/circle-big.png ! \
        decodebin2 ! imagefreeze ! ffmpegcolorspace"

    cat > test.py <<-EOF
	wait_for_match("$testdir/circle-small.png",
	               match_parameters=MatchParameters(erode_passes=2))
	EOF
    stbt-run -v --source-pipeline="$source_pipeline" --control=none test.py \
        || return

    cat > test.py <<-EOF
	wait_for_match("$testdir/circle-small.png",
	               match_parameters=MatchParameters(erode_passes=1))
	EOF
    ! stbt-run -v --source-pipeline="$source_pipeline" --control=none test.py
}

test_wait_for_match_confirm_threshold_affects_match() {
    # This test demonstrates that changing the confirm_threshold parameter
    # can cause incongruent images to match falsely.
    local source_pipeline="filesrc location=$testdir/slight-variation-1.png ! \
        decodebin2 ! imagefreeze ! ffmpegcolorspace"

    cat > test.py <<-EOF
	wait_for_match("$testdir/slight-variation-2.png", timeout_secs=1,
	               match_parameters=MatchParameters(confirm_threshold=0.5))
	EOF
    stbt-run -v --source-pipeline="$source_pipeline" --control=none test.py \
        || return

    cat > test.py <<-EOF
	wait_for_match("$testdir/slight-variation-2.png", timeout_secs=1,
	               match_parameters=MatchParameters(confirm_threshold=0.4))
	EOF
    ! stbt-run -v --source-pipeline="$source_pipeline" --control=none test.py
}

test_wait_for_match_with_pyramid_optimisation_disabled() {
    cat > test.py <<-EOF &&
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF
    sed -e 's/pyramid_levels =.*/pyramid_levels = 1/' \
        "$testdir"/stbt.conf > stbt.conf &&
    STBT_CONFIG_FILE="$scratchdir"/stbt.conf stbt-run -v test.py
}

test_detect_match_nonexistent_template() {
    cat > test.py <<-EOF
	import sys
	m = detect_match("idontexist.png").next()
	sys.exit(0 if m.match else 1)
	EOF
    ! stbt-run -v test.py
}

test_press_until_match() {
    # This doesn't test that press_until_match presses repeatedly, but at least
    # it tests that press_until_match doesn't blow up completely.
    cat > test.py <<-EOF
	press_until_match("checkers-8", "$testdir/videotestsrc-checkers-8.png")
	EOF
    stbt-run -v test.py
}

test_wait_for_match_searches_in_script_directory() {
    cat > test.py <<-EOF
	wait_for_match("in-script-dir.png")
	EOF
    cp "$testdir"/videotestsrc-bw.png in-script-dir.png
    stbt-run -v test.py
}

test_press_until_match_searches_in_script_directory() {
    cat > test.py <<-EOF
	press_until_match("checkers-8", "in-script-dir.png")
	EOF
    cp "$testdir"/videotestsrc-checkers-8.png in-script-dir.png
    stbt-run -v test.py
}

test_detect_match_searches_in_script_directory() {
    cat > test.py <<-EOF
	m = detect_match("in-script-dir.png").next()
	if not m.match:
	    raise Exception("'No match' when expecting match.")
	EOF
    cp "$testdir"/videotestsrc-bw.png in-script-dir.png
    stbt-run -v test.py
}

test_detect_match_searches_in_library_directory() {
    cat > test.py <<-EOF
	import stbt_helpers
	stbt_helpers.find()
	EOF
    mkdir stbt_helpers
    cat > stbt_helpers/__init__.py <<-EOF
	import stbt
	def find():
	    m = stbt.detect_match("in-helpers-dir.png").next()
	    if not m.match:
	        raise Exception("'No match' when expecting match.")
	EOF
    cp "$testdir"/videotestsrc-bw.png stbt_helpers/in-helpers-dir.png
    PYTHONPATH="$PWD:$PYTHONPATH" stbt-run -v test.py
}

test_detect_match_searches_in_caller_directory() {
    cat > test.py <<-EOF
	import stbt_tests
	stbt_tests.find()
	EOF
    mkdir stbt_tests
    cat > stbt_tests/__init__.py <<-EOF
	import stbt_helpers
	def find():
	    stbt_helpers.find("in-caller-dir.png")
	EOF
    mkdir stbt_helpers
    cat > stbt_helpers/__init__.py <<-EOF
	import stbt
	def find(image):
	    m = stbt.detect_match(image).next()
	    if not m.match:
	        raise Exception("'No match' when expecting match.")
	EOF
    cp "$testdir"/videotestsrc-bw.png stbt_tests/in-caller-dir.png
    PYTHONPATH="$PWD:$PYTHONPATH" stbt-run -v test.py
}

test_changing_input_video_with_the_test_control() {
    cat > test.py <<-EOF
	wait_for_match("$testdir/videotestsrc-redblue.png")
	press("checkers-8")
	wait_for_match("$testdir/videotestsrc-checkers-8.png")
	EOF
    stbt-run -v test.py
}

test_detect_match_reports_match() {
    cat > test.py <<-EOF
	# Should report a match
	for match_result in detect_match("$testdir/videotestsrc-redblue.png"):
	    if match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("No match incorrectly reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v test.py
}

test_detect_match_reports_match_position() {
    cat > test.py <<-EOF
	for match_result in detect_match("$testdir/videotestsrc-redblue.png"):
	    if match_result.position.x == 228 and match_result.position.y == 0:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception(
	            "Wrong match position reported, expected: (228,0), "
	            "got %s." % str(match_result.position))
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v test.py
}

test_detect_match_reports_valid_timestamp() {
    cat > test.py <<-EOF
	last_timestamp=None
	for match_result in detect_match("$testdir/videotestsrc-redblue.png"):
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
    stbt-run -v test.py
}

test_detect_match_reports_no_match() {
    cat > test.py <<-EOF
	# Should not report a match
	for match_result in detect_match("$testdir/videotestsrc-checkers-8.png"):
	    if not match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrong match reported.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v test.py
}

test_detect_match_times_out() {
    cat > test.py <<-EOF
	for match_result in detect_match("$testdir/videotestsrc-redblue.png",
	                                 timeout_secs=1):
	    pass
	EOF
    stbt-run -v test.py
}

test_detect_match_times_out_during_yield() {
    cat > test.py <<-EOF
	i = 0
	for match_result in detect_match("$testdir/videotestsrc-redblue.png",
	                                 timeout_secs=1):
	    import time
	    time.sleep(2)
	    i += 1
	assert i == 1
	EOF
    stbt-run -v test.py
}

test_detect_match_changing_template_is_not_racy() {
    # This test can seem a bit complicated, but the race occured even with:
    #   # Supposed to match and matches
    #   wait_for_match("videotestsrc-bw.png", timeout_secs=1)
    #   # Not supposed to match but matches intermittently
    #   wait_for_match("videotestsrc-redblue-flipped.png", timeout_secs=1)
    cat > test.py <<-EOF
	for match_result in detect_match("$testdir/videotestsrc-bw.png",
	                                 timeout_secs=1):
	    if not match_result.match:
	        raise Exception("Match not reported.")
	    # Leave time for another frame to be processed with this template
	    import time
	    time.sleep(1.0) # make sure the test fail (0.1s also works)
	    break
	for match_result in detect_match(
	        "$testdir/videotestsrc-redblue-flipped.png"):
	    # Not supposed to match
	    if not match_result.match:
	        import sys
	        sys.exit(0)
	    else:
	        raise Exception("Wrongly reported a match: race condition.")
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v test.py
}

test_detect_match_example_press_and_wait_for_match() {
    cat > test.py <<-EOF
	key_sent = False
	for match_result in detect_match("$testdir/videotestsrc-checkers-8.png"):
	    if not key_sent:
	        if match_result.match:
	            raise Exception("Wrong match reported.")
	        press("checkers-8")
	        key_sent = True
	    else:
	        if match_result.match:
	            import sys
	            sys.exit(0)
	raise Exception("Timeout occured without any result reported.")
	EOF
    stbt-run -v test.py
}

test_precondition_script() {
    cat > test.py <<-EOF
	from preconditions import *
	checkers_via_gamut()
	wait_for_match(
	    "$testdir/videotestsrc-checkers-8.png")
	EOF
    PYTHONPATH="$testdir:$PYTHONPATH" stbt-run -v test.py
}

test_detect_match_visualisation() {
    cat > detect_match.py <<-EOF &&
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png", consecutive_matches=240)
	EOF
    cat > verify.py <<-EOF &&
	wait_for_match("$testdir/videotestsrc-redblue-with-border.png")
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt-run -v \
        --sink-pipeline 'gdppay ! filesink location=fifo sync=false' \
        detect_match.py &
    trap "kill $!; rm fifo" EXIT

    stbt-run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_match_consecutive_timed_frames() {
    cat > test.py <<-EOF
	img1 = '$testdir/videotestsrc-timed-frame.png'
	img2 = '$testdir/videotestsrc-timed-frame-2.png'
	img3 = '$testdir/videotestsrc-timed-frame-3.png'
	with process_all_frames():
	    res = wait_for_match(img1, timeout_secs=18)
	    t1 = res.timestamp
	    res = wait_for_match(img2)
	    t2 = res.timestamp
	    res = wait_for_match(img3)
	    t3 = res.timestamp
	assert t2 - t1 == 20000000, ('%s and %s did not match in '
	                             'consecutive frames, the time difference '
	                             'is %s' % (img1, img2, str(t2 - t1)))
	assert t3 - t2 == 20000000, ('%s and %s did not match in '
	                             'consecutive frames, the time difference '
	                             'is %s' % (img1, img2, str(t2 - t1)))
	EOF
    stbt-run --source-pipeline="videotestsrc is-live=true ! \
        videorate force-fps=50/1 ! cairotimeoverlay ! ffmpegcolorspace" \
        --sink-pipeline="ximagesink" \
        test.py
}

test_live_stream_caught_up_after_process_all_frames() {
    echo $testdir
    cat > test.py <<-EOF
	wait_for_match('$testdir/videotestsrc-checkers-8.png')
	with process_all_frames():
	    press('smpte')
	    wait_for_match('$testdir/videotestsrc-smpte-corner.png')
	    press('checkers-8')
	wait_for_match('$testdir/videotestsrc-checkers-8.png')
	EOF
    stbt-run --source-pipeline="videotestsrc is-live=true pattern=10 ! \
        ffmpegcolorspace" \
        test.py
}
