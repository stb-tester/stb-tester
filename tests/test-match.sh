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
    ! stbt-run -v test.py
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

test_press_until_match_presses_once() {
    cat > test.py <<-EOF &&
	press_until_match(
	    "checkers-8", "$testdir/videotestsrc-checkers-8.png",
	    interval_secs=1)
	EOF
    stbt-run -v test.py &> test.log || { cat test.log; return 1; }
    [[ "$(grep -c 'Pressed checkers-8' test.log)" == 1 ]] ||
        { cat test.log; fail "Didn't see exactly 1 keypress"; }
}

test_press_until_match_presses_zero_times_if_match_already_present() {
    cat > test.py <<-EOF
	press_until_match("smpte", "$testdir/videotestsrc-redblue.png")
	EOF
    stbt-run -v test.py &> test.log || { cat test.log; return 1; }
    [[ "$(grep -c 'Pressed smpte' test.log)" == 0 ]] ||
        { cat test.log; fail "Saw > 0 keypresses"; }
}

test_press_until_match_max_presses() {
    cat > test.py <<-EOF &&
	press_until_match(
	    "ball", "$testdir/videotestsrc-checkers-8.png",
	    interval_secs=1, max_presses=3)
	EOF
    ! stbt-run -v test.py &> test.log || fail "Expected MatchTimeout"
    [[ "$(grep -c 'Pressed ball' test.log)" == 3 ]] ||
        { cat test.log; fail "Didn't see exactly 3 keypresses"; }
}

test_press_until_match_reads_interval_secs_from_config_file() {
    cat > test-3s.py <<-EOF &&
	import stbt
	start = stbt._display.get_frame().timestamp
	match = press_until_match(
	    "checkers-8", "$testdir/videotestsrc-checkers-8.png")
	assert (match.timestamp - start) >= 3e9, (
	    "Took %dns; expected >=3s" % (match.timestamp - start))
	EOF
    cp "$testdir"/stbt.conf . &&
    STBT_CONFIG_FILE="$scratchdir"/stbt.conf stbt-run -v test-3s.py &&

    cat > test-1s.py <<-EOF &&
	import stbt
	start = stbt._display.get_frame().timestamp
	match = press_until_match(
	    "checkers-8", "$testdir/videotestsrc-checkers-8.png")
	assert (match.timestamp - start) < 3e9, (
	    "Took %dns; expected <3s" % (match.timestamp - start))
	EOF
    sed -e 's/interval_secs =.*/interval_secs = 1/' \
        stbt.conf > stbt.conf~ && mv stbt.conf~ stbt.conf &&
    STBT_CONFIG_FILE="$scratchdir"/stbt.conf stbt-run -v test-1s.py
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

test_that_matchtimeout_screenshot_doesnt_include_visualisation() {
    cat > test.py <<-EOF &&
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF
    ! stbt-run -v --source-pipeline 'videotestsrc pattern=black' test.py &&

    # sqdiff-normed & ccorr-normed give incorrect result on all-black images
    stbt templatematch screenshot.png "$testdir"/black-full-frame.png \
        match_method=ccoeff-normed
}
