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
            "expected 'no element \"viddily-boo\"', " \
            "it was '$(tail -n1 stbt.log)'"
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

test_that_wait_until_returns_on_success() {
    cat > test.py <<-EOF
	import stbt
	count = 0
	def t():
	    global count
	    count += 1
	    return True
	assert stbt.wait_until(t)
	assert count == 1, "Unexpected count %d" % count
	EOF
    stbt run -v test.py
}

test_that_wait_until_times_out() {
    cat > test.py <<-EOF
	import time, stbt
	start = time.time()
	assert not stbt.wait_until(lambda: False, timeout_secs=1)
	end = time.time()
	assert 1 < end - start < 2, \
	    "wait_until took too long (%ds)" % (end - start)
	EOF
    stbt run -v test.py
}

test_that_video_index_is_written_on_eos() {
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
    "$testdir"/webminspector/webminspector.py video.webm &> webminspector.log &&
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
	print "value: %s" % stbt._dut._display.restart_source_enabled
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

test_clock_visualisation() {
    PYTHONPATH="$srcdir" python -c "import stbt, _stbt.core, distutils, sys; \
        sys.exit(0 if (_stbt.core._tesseract_version() \
                       >= distutils.version.LooseVersion('3.03')) else 77)"
    case $? in
        0) true;;
        77) skip "Requires tesseract >= 3.03 for 'tesseract_user_patterns'";;
        *) fail "Probing tesseract version failed";;
    esac

    cat > test.py <<-EOF &&
	import time
	time.sleep(60)
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline 'videotestsrc pattern=black is-live=true' \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        test.py &
    test_script=$!
    trap "kill $test_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import datetime, time, stbt
	
	def read_time(frame):
	    s = stbt.ocr(
	        frame, mode=stbt.OcrMode.SINGLE_LINE,
	        tesseract_user_patterns=["\d\d:\d\d:\d\d.\d\d"],
	        region=stbt.Region(x=5, y=5, right=200, bottom=35)).replace(" ", "")
	    d = datetime.date.today()
	    return datetime.datetime(
	        d.year, d.month, d.day, int(s[0:2]), int(s[3:5]), int(s[6:8]),
	        int(s[9]) * 100000)
	
	seconds = lambda n: datetime.timedelta(seconds=n)
	
	frame = stbt.get_frame()
	pre_ocr = time.time()
	start = read_time(frame)
	ocr_duration = time.time() - pre_ocr  # ocr can take >1s to run.
	time.sleep(1)
	end = read_time(stbt.get_frame())
	diff = end - start
	assert seconds(0.9) < diff < seconds(2 + ocr_duration), \
	    "Unexpected time diff %s between %s and %s" % (diff, end, start)
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_template_annotation_labels() {
    cat > test.py <<-EOF &&
	import stbt
	for _ in stbt.detect_match("${testdir}/videotestsrc-checkers-8.png"):
	    pass
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline 'videotestsrc is-live=true' \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        test.py &
    test_script=$!
    trap "kill $test_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import stbt
	stbt.wait_for_match("${testdir}/videotestsrc-checkers-8-label.png")
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_template_annotation_with_ndarray_template() {
    cat > test.py <<-EOF &&
	import stbt, numpy as np
	template = np.ones(shape=(100, 100, 3), dtype=np.uint8)
	template *= [0, 255, 0]  # green
	stbt.save_frame(template, 'template.png')
	for _ in stbt.detect_match(template):
	    pass
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline 'videotestsrc is-live=true' \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        test.py &
    test_script=$!
    trap "kill $test_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import stbt
	stbt.save_frame(stbt.get_frame(), "test.png")
	stbt.wait_for_match("${testdir}/custom-image-label.png")
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
	assert time2 - time1 >= datetime.timedelta(seconds=0.45), (
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
