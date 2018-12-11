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
    cat stbt.log
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
	assert stbt.get_config("global", "should_be_true", type_=bool) is True
	assert stbt.get_config("global", "should_be_false", type_=bool) is False
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
	for frame in frames:
	    black = stbt.is_screen_black(frame)
	    print "%s: %s" % (frame.time, black)
	    if black:
	        break
	assert black, "Failed to find black screen"
	for frame in frames:
	    black = stbt.is_screen_black(frame)
	    print "%s: %s" % (frame.time, black)
	    if not black:
	        break
	assert not black, "Failed to find non-black screen"
	EOF
    stbt run -v test.py
}

test_that_frames_doesnt_deadlock() {
    cat > test.py <<-EOF &&
	import stbt
	for frame in stbt.frames():
	    print frame.time
	    break
	for frame in stbt.frames():
	    print frame.time
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
    PYTHONPATH="$srcdir" python -c "import stbt, _stbt.ocr, distutils, sys; \
        sys.exit(0 if (_stbt.ocr._tesseract_version() \
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
	            region=stbt.Region(x=5, y=5, right=200, bottom=35)) \\
	        .replace(" ", "") \\
	        .replace("O", "0")
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

test_that_visualisation_doesnt_write_to_user_frame() {
    cat > test.py <<-EOF
	import numpy, stbt, time
	
	f = stbt.get_frame()
	orig = f.copy()
	stbt.draw_text("Hello")
	time.sleep(1)  # wait for sink pipeline buffer to process the frame
	# Can't use is_screen_black because on ubuntu 14.04 videotestsrc
	# has a green bar along the bottom of the frame.
	assert numpy.all(f == orig)
	EOF
    stbt run -v \
        --source-pipeline 'videotestsrc pattern=black is-live=true' \
        --save-video=video.webm \
        test.py
}

test_that_frames_are_read_only() {
    cat > test.py <<-EOF
	import stbt
	
	f = stbt.get_frame()
	try:
	    f[0,0,0] = 0
	    assert False, "Frame from stbt.get_frame is writeable"
	except (ValueError, RuntimeError):
	    # Different versions of numpy raise different exceptions
	    pass
	
	for f in stbt.frames():
	    try:
	        f[0,0,0] = 0
	        assert False, "frame from stbt.frames is writeable"
	    except (ValueError, RuntimeError):
	        pass
	    break
	
	class F(stbt.FrameObject):
	    pass
	f = F()
	try:
	    f._frame[0,0,0] = 0
	    assert False, "stbt.FrameObject._frame is writeable"
	except (ValueError, RuntimeError):
	    pass
	
	m = stbt.match("$testdir/videotestsrc-redblue.png")
	try:
	    m.frame[0,0,0] = 0
	    assert False, "stbt.MatchResult.frame is writeable"
	except (ValueError, RuntimeError):
	    pass
	EOF
    stbt run -v test.py
}

test_that_get_frame_time_is_wall_time() {
    cat > test.py <<-EOF &&
	import stbt, time

	f = stbt.get_frame()
	t = time.time()

	print "stbt.get_frame().time:", f.time
	print "time.time():", t
	print "latency:", t - f.time

	# get_frame() gives us the last frame that arrived.  This may arrived a
	# little time ago and have been waiting in a buffer.
	assert t - 0.1 < f.time < t
	EOF

    stbt run -vv test.py
}

test_template_annotation_labels() {
    cat > test.py <<-EOF &&
	import stbt
	for _ in stbt.detect_match("${testdir}/videotestsrc-checkers-8.png"):
	    pass
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline 'videotestsrc is-live=true ! video/x-raw,width=640' \
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
	template *= np.array([0, 255, 0], dtype=np.uint8)  # green
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
	time1 = datetime.datetime.now()
	stbt.press('OK')
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

test_multithreaded() {
    cat > test.py <<-EOF &&
	import sys, time
	from multiprocessing.pool import ThreadPool
	
	import stbt
	
	stbt.press('black')
	assert stbt.wait_until(stbt.is_screen_black)
	
	# Kick off the threads
	pool = ThreadPool(processes=2)
	result_iter = pool.imap_unordered(apply, [
	    lambda: wait_for_motion(timeout_secs=2),
	    lambda: wait_for_match(
	        "$testdir/videotestsrc-checkers-8.png", timeout_secs=2)
	])
	
	# Change the pattern
	stbt.press(sys.argv[1])
	
	# See which matched
	result = result_iter.next()
	if isinstance(result, MotionResult):
	    print "Motion"
	elif isinstance(result, MatchResult):
	    print "Checkers"
	EOF

    stbt run -v test.py checkers-8 >out.log
    grep -q "Checkers" out.log || fail "Expected checkers pattern"

    stbt run -v test.py smpte >out.log
    grep -q "Motion" out.log || fail "Expected motion"

    stbt run -v test.py black >out.log
    grep -q "Timeout" out.log || fail "Expected timeout"
}

test_global_use_old_threading_behaviour() {
    cat > test.py <<-EOF &&
	ts = set()
	for _ in range(10):
	    ts.add(stbt.get_frame().time)
	print "Saw %i unique frames" % len(ts)
	assert len(ts) < 5
	EOF
    stbt run test.py 2>stderr.log || fail "Incorrect get_frame() behaviour"
    ! grep -q "stb-tester/stb-tester/pull/449" stderr.log \
        || fail "use_old_threading_behaviour warning shouldn't be printed"
}

test_global_use_old_threading_behaviour_frames() {
    cat > test.py <<-EOF &&
	import itertools
	sa = set()
	sb = set()
	for a, b in itertools.izip(stbt.frames(), stbt.frames()):
	    if len(sa) >= 10:
	        break
	    sa.add(a.time)
	    sb.add(b.time)
	print sorted(sa)
	print sorted(sb)
	assert len(sa) == 10
	assert len(sb) == 10
	# sa and sb contain the same frames:
	assert sa == sb
	EOF
    stbt run -vv test.py ||
        fail "Incorrect frames() behaviour (use_old_threading_behaviour=false)"
}
