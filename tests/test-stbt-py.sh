# Run with ./run-tests.sh

test_that_invalid_control_doesnt_hang() {
    touch test.py
    timeout 10 stbt run -v --control asdf test.py
    local ret=$?
    [ $ret -ne $timedout ] || fail "'stbt run --control asdf' timed out"
}

test_invalid_source_pipeline() {
    touch test.py
    stbt run -v --source-pipeline viddily-boo test.py &> stbt.log
    tail -n1 stbt.log | grep -q 'no element "viddily-boo"' ||
        fail "The last error message in '$scratchdir/stbt.log' wasn't the" \
            "expected 'no element \"viddily-boo\"'"
}

test_get_frame_and_save_frame() {
    cat > get-screenshot.py <<-EOF
	wait_for_match("$testdir/videotestsrc-redblue.png")
	press("gamut")
	wait_for_match("$testdir/videotestsrc-gamut.png")
	save_frame(get_frame(), "gamut.png")
	EOF
    stbt run -v get-screenshot.py
    [ -f gamut.png ] ||
        fail "Screenshot '$scratchdir/gamut.png' wasn't created"

    cat > match-screenshot.py <<-EOF
	press("gamut")
	# confirm_threshold accounts for match rectangle in the screenshot.
	wait_for_match("gamut.png",
	               match_parameters=MatchParameters(confirm_threshold=0.7))
	EOF
    stbt run -v match-screenshot.py
}

test_get_config() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.get_config("global", "test_key") == "this is a test value"
	assert stbt.get_config("special", "test_key") == \
	    "not the global value"
	try:
	    stbt.get_config("global", "no_such_key")
	    assert False
	except ConfigurationError:
	    pass
	try:
	    stbt.get_config("no_such_section", "test_key")
	    assert False
	except ConfigurationError:
	    pass
	try:
	    stbt.get_config("special", "not_special")
	    assert False
	except ConfigurationError:
	    pass
	EOF
    stbt run -v test.py
}

test_that_frames_returns_at_least_one_frame() {
    cat > test.py <<-EOF
	import stbt
	stbt.frames(timeout_secs=0).next()
	stbt.frames(timeout_secs=0).next()
	EOF
    stbt run -v test.py
}

test_that_frames_doesnt_time_out() {
    cat > test.py <<-EOF
	import stbt
	for _ in stbt.frames():
	    pass
	EOF
    timeout 12 stbt run -v test.py
    local ret=$?
    [ $ret -eq $timedout ] || fail "Unexpected exit status '$ret'"
}

test_that_frames_raises_NoVideo() {
    cat > test.py <<-EOF
	import stbt
	for _ in stbt.frames():
	    pass
	EOF
    stbt run -v \
        --source-pipeline "videotestsrc ! identity sleep-time=12000000" \
        test.py &> stbt-run.log
    grep NoVideo stbt-run.log ||
        fail "'stbt.frames' didn't raise 'NoVideo' exception"
}

test_using_frames_to_measure_black_screen() {
    cat > test.py <<-EOF &&
	import cv2
	import stbt
	import threading
	import time
	
	def presser():
	    time.sleep(1)
	    stbt.press("black")
	    time.sleep(1)
	    stbt.press("smpte")
	
	threading.Thread(target=presser).start()
	
	frames = stbt.frames(timeout_secs=10)
	for frame, timestamp in frames:
	    black = stbt.is_screen_black(frame)
	    print "%s: %s" % (timestamp, black)
	    if black:
	        break
	assert black, "Failed to find black screen"
	for frame, timestamp in frames:
	    black = stbt.is_screen_black(frame)
	    print "%s: %s" % (timestamp, black)
	    if not black:
	        break
	assert not black, "Failed to find non-black screen"
	EOF
    stbt run -v test.py
}

test_that_frames_doesnt_deadlock() {
    cat > test.py <<-EOF &&
	import stbt
	for frame, timestamp in stbt.frames():
	    print timestamp
	    break
	for frame, timestamp in stbt.frames():
	    print timestamp
	    break
	frames = stbt.frames()
	frame1 = frames.next()
	frames = stbt.frames()  # Drop reference to old 'frames'; should be GCd.
	frame2 = frames.next()
	frames3 = stbt.frames()
	frame3 = frames3.next()  # old 'frames' still holds lock
	EOF
    timeout 10 stbt run -v test.py &&

    cat > test2.py <<-EOF
EOF
}

test_that_is_screen_black_is_true_for_black_pattern() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.is_screen_black()
	EOF
    stbt run -v \
        --source-pipeline 'videotestsrc pattern=black is-live=true ! video/x-raw,format=BGR' \
        test.py
}

test_that_is_screen_black_is_false_for_smpte_pattern() {
    cat > test.py <<-EOF
	import stbt
	assert not stbt.is_screen_black()
	EOF
    stbt run -v \
        --source-pipeline 'videotestsrc pattern=smpte is-live=true ! video/x-raw,format=BGR' \
        test.py
}

test_that_is_screen_black_is_true_for_smpte_pattern_when_masked() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.is_screen_black(
	    mask="$testdir/videotestsrc-mask-non-black.png"
	)
	EOF
    stbt run -v \
        --source-pipeline 'videotestsrc pattern=smpte is-live=true ! video/x-raw,format=BGR' \
        test.py
}

test_is_screen_black_threshold_bounds_for_almost_black_frame() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.is_screen_black(threshold=3)
	assert not stbt.is_screen_black(threshold=2)
	EOF
    stbt run -v --control none \
        --source-pipeline \
            "filesrc location=$testdir/almost-black.png ! decodebin !
             imagefreeze" \
        test.py
}

test_that_is_screen_black_reads_default_threshold_from_stbt_conf() {
    set_config is_screen_black.threshold "0" &&
    cat > test.py <<-EOF &&
	assert not stbt.is_screen_black()
	EOF
    stbt run -v --control none \
        --source-pipeline \
            "filesrc location=$testdir/almost-black.png ! decodebin !
             imagefreeze" \
        test.py
}

test_that_is_screen_black_threshold_parameter_overrides_default() {
    set_config is_screen_black.threshold "0" &&
    cat > test.py <<-EOF &&
	assert stbt.is_screen_black(threshold=3)
	EOF
    stbt run -v --control none \
        --source-pipeline \
            "filesrc location=$testdir/almost-black.png ! decodebin !
             imagefreeze" \
        test.py
}

test_that_is_screen_black_respects_passed_in_frame() {
    cat > test.py <<-EOF
	import cv2
	import stbt
	almost_black = cv2.imread("$testdir/almost-black.png")
	assert not stbt.is_screen_black(almost_black, threshold=0)
	assert stbt.is_screen_black(almost_black, threshold=3)
	EOF
    stbt run -v test.py
}

test_that_is_screen_black_writes_debugging_information() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.is_screen_black()
	EOF
    stbt run -vv \
        --source-pipeline 'videotestsrc pattern=black is-live=true ! video/x-raw,format=BGR' \
        test.py \
    || fail "Test should have detected black"

    [ -e "stbt-debug/is_screen_black/00001/source.png" ] \
        || fail "source debug image not written"
    [ -e "stbt-debug/is_screen_black/00001/non-black-regions-after-masking.png" ] \
        || fail "source debug image not written"
}

test_that_is_screen_black_with_mask_writes_debugging_information() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.is_screen_black(
	    mask="$testdir/videotestsrc-mask-non-black.png"
	)
	EOF
    stbt run -vv \
        --source-pipeline 'videotestsrc pattern=smpte is-live=true ! video/x-raw,format=BGR' \
        test.py \
    || fail "Test should have detected black"

    [ -e "stbt-debug/is_screen_black/00001/source.png" ] \
        || fail "source debug image not written"
    [ -e "stbt-debug/is_screen_black/00001/mask.png" ] \
        || fail "source debug image not written"
    [ -e "stbt-debug/is_screen_black/00001/non-black-regions-after-masking.png" ] \
        || fail "source debug image not written"
}

test_that_video_index_is_written_on_eos() {
    which webminspector.py &>/dev/null \
        || skip "webminspector.py not found. See https://chromium.googlesource.com/webm/webminspector/"

    _test_that_video_index_is_written_on_eos 5 && return
    echo "Failed with 5s video; trying again with 20s video"
    _test_that_video_index_is_written_on_eos 20
}
_test_that_video_index_is_written_on_eos() {
    cat > test.py <<-EOF &&
	import time
	time.sleep($1)
	EOF
    stbt run -v \
        --sink-pipeline \
            "queue ! vp8enc cpu-used=6 ! webmmux ! filesink location=video.webm" \
        test.py &&
    webminspector.py video.webm &> webminspector.log &&
    grep "Cue Point" webminspector.log || {
      cat webminspector.log
      echo "error: Didn't find 'Cue Point' in $scratchdir/webminspector.log"
      return 1
    }
}

test_save_video() {
    cat > record.py <<-EOF &&
	import time
	time.sleep(2)
	EOF
    set_config run.save_video "video.webm" &&
    stbt run -v record.py &&
    cat > test.py <<-EOF &&
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF
    set_config run.save_video "" &&
    timeout 10 stbt run -v --control none \
        --source-pipeline 'filesrc location=video.webm' \
        test.py
}

test_that_verbosity_level_is_read_from_config_file() {
    set_config global.verbose "2" &&
    touch test.py &&
    stbt run test.py &&
    cat log | grep "verbose: 2"
}

test_that_verbose_command_line_argument_overrides_config_file() {
    set_config global.verbose "2" &&
    touch test.py &&
    stbt run -v test.py &&
    cat log | grep "verbose: 1"
}

test_that_restart_source_option_is_read() {
    cat > test.py <<-EOF &&
	import stbt
	print "value: %s" % stbt._display.restart_source_enabled
	EOF
    # Read from the command line
    stbt run -v --restart-source --control none test.py &&
    cat log | grep "restart_source: True" &&
    cat log | grep "value: True" &&
    echo > log &&
    # Read from the config file
    set_config global.restart_source "True" &&
    stbt run -v --control none test.py &&
    cat log | grep "restart_source: True" &&
    cat log | grep "value: True"
}

test_press_visualisation() {
    cat > press.py <<-EOF &&
	import signal, time
	def press_black(signo, frame):
	    press("black")
	    time.sleep(60)
	def press_black_and_red(signo, frame):
	    press("black")
	    press("red")
	    time.sleep(60)
	signal.signal(signal.SIGUSR1, press_black)
	signal.signal(signal.SIGUSR2, press_black_and_red)
	time.sleep(60)
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        press.py &
    press_script=$!
    trap "kill $press_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import os, signal
	wait_for_match("$testdir/videotestsrc-redblue.png")
	os.kill($press_script, signal.SIGUSR1)
	wait_for_match("$testdir/black.png")
	os.kill($press_script, signal.SIGUSR2)
	wait_for_match("$testdir/red-black.png")
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_draw_text() {
    cat > draw-text.py <<-EOF &&
	import stbt
	from time import sleep
	stbt.draw_text("Test", duration_secs=60)
	sleep(60)
	EOF
    cat > verify-draw-text.py <<-EOF &&
	import stbt
	wait_for_match("$testdir/draw-text.png")
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v --control none \
        --source-pipeline 'videotestsrc is-live=true pattern=white' \
        --sink-pipeline 'gdppay ! filesink location=fifo sync=false' \
        draw-text.py &
    trap "kill $!; rm fifo" EXIT

    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify-draw-text.py
}

test_that_press_waits_between_subsequent_presses() {
    cat > test.py <<-EOF &&
	import stbt, datetime
	stbt.press('OK')
	time1 = datetime.datetime.now()
	stbt.press('OK', interpress_delay_secs=0.5)
	time2 = datetime.datetime.now()
	assert time2 - time1 >= datetime.timedelta(seconds=0.5), (
	    "Expected: >= 0:00:00.5, got: %s between presses" % (time2 - time1))
	EOF
    stbt run -v --control none test.py
}

test_that_press_doesnt_wait_any_longer_than_necessary() {
    cat > test.py <<-EOF &&
	import stbt, time
	
	def fake_sleep(x):
	    assert False, "Unexpected call to time.sleep"
	
	stbt.press('OK')
	time.sleep(0.1)
	time.sleep = fake_sleep
	stbt.press('OK', interpress_delay_secs=0.1)
	EOF
    stbt run -v --control none test.py
}

test_that_press_reads_default_delay_from_stbt_conf() {
    set_config press.interpress_delay_secs "0.5" &&
    cat > test.py <<-EOF &&
	import stbt, datetime
	stbt.press('OK')
	time1 = datetime.datetime.now()
	stbt.press('OK')
	time2 = datetime.datetime.now()
	assert time2 - time1 >= datetime.timedelta(seconds=0.5), (
	    "Expected: >= 0:00:00.5, got: %s between presses" % (time2 - time1))
	EOF
    stbt run -v --control none test.py
}

test_that_transformation_pipeline_transforms_video() {
    set_config global.transformation_pipeline \
        "videoflip method=horizontal-flip"
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=0)
	EOF
    stbt run -v test.py || fail "Video was not flipped"

    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png", timeout_secs=0)
	EOF
    ! stbt run -v test.py || fail "Test invalid, shouldn't have matched"
}

test_backwards_compatibility_with_UITestFailure() {
    cat > test.py <<-EOF &&
	import stbt
	
	try:
	    raise stbt.UITestFailure()
	except stbt.TestFailure:
	    print "Caught UITestFailure as TestFailure"
	
	try:
	    raise stbt.TestFailure()
	except stbt.UITestFailure:
	    print "Caught TestFailure as UITestFailure"
	
	try:
	    raise stbt.MatchTimeout(None, None, None)
	except stbt.UITestFailure:
	    print "Caught MatchTimeout as UITestFailure"
	
	try:
	    raise stbt.MatchTimeout(None, None, None)
	except stbt.TestFailure:
	    print "Caught MatchTimeout as TestFailure"
	EOF
    stbt run -v test.py
}
