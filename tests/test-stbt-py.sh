# Run with ./run-tests.sh

test_that_invalid_control_doesnt_hang() {
    touch test.py
    $timeout 10 stbt run -v --control asdf test.py
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
	from stbt_core import get_frame, press, save_frame, wait_for_match
	wait_for_match("$testdir/videotestsrc-redblue.png")
	press("gamut")
	wait_for_match("$testdir/videotestsrc-gamut.png")
	save_frame(get_frame(), "gamut.png")
	EOF
    stbt run -v get-screenshot.py
    [ -f gamut.png ] ||
        fail "Screenshot '$scratchdir/gamut.png' wasn't created"

    cat > match-screenshot.py <<-EOF
	from stbt_core import MatchParameters, press, wait_for_match
	press("gamut")
	# confirm_threshold accounts for match rectangle in the screenshot.
	wait_for_match("gamut.png",
	               match_parameters=MatchParameters(confirm_threshold=0.3))
	EOF
    stbt run -v match-screenshot.py
}

test_get_config() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	assert stbt.get_config("global", "test_key") == "this is a test value"
	assert stbt.get_config("special", "test_key") == \
	    "not the global value"
	assert stbt.get_config("global", "should_be_true", type_=bool) is True
	assert stbt.get_config("global", "should_be_false", type_=bool) is False
	try:
	    stbt.get_config("global", "no_such_key")
	    assert False
	except stbt.ConfigurationError:
	    pass
	try:
	    stbt.get_config("no_such_section", "test_key")
	    assert False
	except stbt.ConfigurationError:
	    pass
	try:
	    stbt.get_config("special", "not_special")
	    assert False
	except stbt.ConfigurationError:
	    pass
	EOF
    stbt run -v test.py
}

test_that_frames_returns_at_least_one_frame() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	next(stbt.frames(timeout_secs=0))
	next(stbt.frames(timeout_secs=0))
	EOF
    stbt run -v test.py
}

test_that_frames_doesnt_time_out() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	for _ in stbt.frames():
	    pass
	EOF
    $timeout 12 stbt run -v test.py
    local ret=$?
    [ $ret -eq $timedout ] || fail "Unexpected exit status '$ret'"
}

test_that_frames_raises_NoVideo_on_underrun() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	for _ in stbt.frames():
	    pass
	EOF
    stbt run -v \
        --source-pipeline "videotestsrc ! identity sleep-time=12000000" \
        test.py &> stbt-run.log
    grep NoVideo stbt-run.log ||
        fail "'stbt.frames' didn't raise 'NoVideo' exception"
}

test_that_frames_raises_NoVideo_on_eos() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	for _ in stbt.frames():
	    pass
	EOF
    stbt run -v \
        --source-pipeline "videotestsrc num-buffers=1" \
        test.py &> stbt-run.log
    grep NoVideo stbt-run.log ||
        fail "'stbt.frames' didn't raise 'NoVideo' exception"
}

test_using_frames_to_measure_black_screen() {
    cat > test.py <<-EOF &&
	import cv2
	import stbt_core as stbt
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
	    print("%s: %s" % (frame.time, black))
	    if black:
	        break
	assert black, "Failed to find black screen"
	for frame in frames:
	    black = stbt.is_screen_black(frame)
	    print("%s: %s" % (frame.time, black))
	    if not black:
	        break
	assert not black, "Failed to find non-black screen"
	EOF
    stbt run -v test.py
}

test_that_frames_doesnt_deadlock() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	for frame in stbt.frames():
	    print(frame.time)
	    break
	for frame in stbt.frames():
	    print(frame.time)
	    break
	frames = stbt.frames()
	frame1 = next(frames)
	frames = stbt.frames()  # Drop reference to old 'frames'; should be GCd.
	frame2 = next(frames)
	frames3 = stbt.frames()
	frame3 = next(frames3)  # old 'frames' still holds lock
	EOF
    local t
    $timeout 10 stbt run -v test.py
}

test_that_is_screen_black_reads_default_threshold_from_stbt_conf() {
    set_config is_screen_black.threshold "0" &&
    cat > test.py <<-EOF &&
	import stbt_core as stbt
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
	import stbt_core as stbt
	assert stbt.is_screen_black(threshold=3)
	EOF
    stbt run -v --control none \
        --source-pipeline \
            "filesrc location=$testdir/almost-black.png ! decodebin !
             imagefreeze" \
        test.py
}

test_that_video_index_is_written_on_eos() {
    cat > test.py <<-EOF &&
	import time
	time.sleep(1)
	EOF
    stbt run -v \
        --sink-pipeline \
            "queue ! x264enc ! mp4mux ! filesink location=video.mp4" \
        test.py &&
    gst-launch-1.0 filesrc location=video.mp4 ! qtdemux ! fakesink
}

test_save_video() {
    cat > record.py <<-EOF &&
	import time
	time.sleep(2)
	EOF
    set_config run.save_video "video.webm" &&
    stbt run -v record.py &&
    cat > test.py <<-EOF &&
	from stbt_core import wait_for_match
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF
    set_config run.save_video "" &&
    $timeout 10 stbt run -v --control none \
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

test_press_visualisation() {
    cat > press.py <<-EOF &&
	import signal, time, stbt_core as stbt
	def press_black(signo, frame):
	    stbt.press("black")
	    time.sleep(60)
	def press_black_and_red(signo, frame):
	    stbt.press("black")
	    stbt.press("red")
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
	import os, signal, stbt_core as stbt
	stbt.wait_for_match("$testdir/videotestsrc-redblue.png")
	os.kill($press_script, signal.SIGUSR1)
	stbt.wait_for_match("$testdir/black.png")
	os.kill($press_script, signal.SIGUSR2)
	stbt.wait_for_match("$testdir/red-black.png")
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_clock_visualisation() {
    PYTHONPATH="$srcdir" $python -c "import _stbt.ocr, sys; \
        sys.exit(0 if _stbt.ocr._tesseract_version() >= [3, 3] else 77)"
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
	import datetime, time, stbt_core as stbt
	
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
	import numpy, stbt_core as stbt, time
	
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
	import stbt_core as stbt
	
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
	import stbt_core as stbt, os, time

	f = stbt.get_frame()
	t = time.time()

	print("stbt.get_frame().time: %.6f" % f.time)
	print("time.time(): %.6f" % t)
	print("latency: %.6f" % (t - f.time))

	# get_frame() gives us the last frame that arrived.  This may arrived a
	# little time ago and have been waiting in a buffer.
	assert t - 0.1 < f.time < t
	EOF

    stbt run -vv test.py
}

test_template_annotation_labels() {
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.TEST_PACK_ROOT = "${testdir}"
	for frame in stbt.frames(timeout_secs=20):
	    stbt.match("${testdir}/videotestsrc-ball.png", frame)
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline "videotestsrc is-live=true pattern=ball ! \
                           video/x-raw,width=640" \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        --save-screenshot never \
        test.py &
    test_script=$!
    trap "kill $test_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import stbt_core as stbt
	stbt.wait_for_match("${testdir}/videotestsrc-ball-label.png")
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify.py
}

test_template_annotation_with_ndarray_template() {
    cat > test.py <<-EOF &&
	import cv2, stbt_core as stbt
	template = cv2.imread("${testdir}/videotestsrc-ball.png")
	assert template is not None
	for frame in stbt.frames(timeout_secs=20):
	    stbt.match(template, frame)
	EOF
    mkfifo fifo || fail "Initial test setup failed"

    stbt run -v \
        --source-pipeline "videotestsrc is-live=true pattern=ball ! \
                           video/x-raw,width=640" \
        --sink-pipeline 'gdppay ! filesink location=fifo' \
        --save-screenshot never \
        test.py &
    test_script=$!
    trap "kill $test_script; rm fifo" EXIT

    cat > verify.py <<-EOF &&
	import stbt_core as stbt
	stbt.wait_for_match("${testdir}/custom-image-label.png")
	EOF
    stbt run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        --save-video video.webm \
        verify.py
}

test_draw_text() {
    # On CircleCI this is failing often (always?) with first_pass_result=0.9519.
    #
    # For comparison:
    #
    #     $ ./stbt_match.py -v tests/white-full-frame.png tests/draw-text.png
    #     first_pass_result=0.2688
    #
    #     $ ./stbt_match.py -v tests/black-full-frame.png tests/draw-text.png
    #     first_pass_result=0.9138
    #
    # This is slightly higher than white-full-frame.png because it matches part
    # of the black background behind the time that we draw on the video; but
    # it's still less than 0.95:
    #
    #     $ cat test.py
    #     import stbt_core as stbt
    #     stbt.wait_for_match("tests/draw-text.png")
    #     $ ./stbt_run.py -v --source-pipeline 'videotestsrc pattern=white' test.py
    #     first_pass_result=0.2816
    #
    cat > draw-text.py <<-EOF &&
	import stbt_core as stbt
	from time import sleep
	stbt.draw_text("Test", duration_secs=60)
	sleep(60)
	EOF
    cat > verify-draw-text.py <<-EOF &&
	import os, stbt_core as stbt
	stbt.wait_for_match("$testdir/draw-text.png", timeout_secs=10)
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
	import stbt_core as stbt, datetime
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
	import stbt_core as stbt, time
	
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
	import stbt_core as stbt, datetime
	stbt.press('OK')
	time1 = datetime.datetime.now()
	stbt.press('OK')
	time2 = datetime.datetime.now()
	assert time2 - time1 >= datetime.timedelta(seconds=0.45), (
	    "Expected: >= 0:00:00.5, got: %s between presses" % (time2 - time1))
	EOF
    stbt run -v --control none test.py
}

test_multithreaded() {
    cat > test.py <<-EOF &&
	import sys, time
	from multiprocessing.pool import ThreadPool
	
	import stbt_core as stbt
	
	stbt.press('black')
	assert stbt.wait_until(stbt.is_screen_black)
	
	# Kick off the threads
	pool = ThreadPool(processes=2)
	result_iter = pool.imap_unordered(
	    lambda f: f(),
	    [
	        lambda: stbt.wait_for_motion(timeout_secs=2),
	        lambda: stbt.wait_for_match(
	            "$testdir/videotestsrc-checkers-8.png",
	            timeout_secs=2),
	    ],
	    chunksize=1)
	
	# Change the pattern
	stbt.press(sys.argv[1])
	
	# See which matched
	result = result_iter.next()
	if isinstance(result, stbt.MotionResult):
	    print("Motion")
	elif isinstance(result, stbt.MatchResult):
	    print("Checkers")
	EOF

    stbt run -v test.py checkers-8 >out.log
    grep -q "Checkers" out.log || fail "Expected checkers pattern"

    stbt run -v test.py smpte >out.log
    grep -q "Motion" out.log || fail "Expected motion"

    stbt run -v test.py black >out.log
    grep -q "Timeout" out.log || fail "Expected timeout"
}

test_that_get_frame_may_return_the_same_frame_twice() {
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	ts = set()
	for _ in range(10):
	    ts.add(stbt.get_frame().time)
	print("Saw %i unique frames" % len(ts))
	assert len(ts) < 5
	EOF
    stbt run test.py || fail "Incorrect get_frame() behaviour"
}

test_that_two_frames_iterators_can_return_the_same_frames_as_each_other() {
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	try:
	    from itertools import izip as zip
	except ImportError:
	    pass
	sa = set()
	sb = set()
	for a, b in zip(stbt.frames(), stbt.frames()):
	    if len(sa) >= 2:
	        break
	    sa.add(a.time)
	    sb.add(b.time)
	print(sorted(sa))
	print(sorted(sb))
	# sa and sb contain the same frames:
	assert sa == sb
	EOF
    stbt run -vv \
        --source-pipeline="videotestsrc is-live=true ! \
            video/x-raw,format=BGR,width=320,height=240,framerate=2/1" \
        test.py || fail "Incorrect frames() behaviour"
}

test_that_press_returns_a_pressresult() {
    cat > test.py <<-EOF &&
	import time, stbt_core as stbt
	
	assert stbt.last_keypress() is None

	before = time.time()
	result1 = stbt.press("KEY_MENU")
	after = time.time()

	assert before < result1.start_time < result1.end_time < after
	assert result1.key == "KEY_MENU"
	assert isinstance(result1.frame_before, stbt.Frame)
	assert stbt.last_keypress() == result1

	before = time.time()
	result2 = stbt.press("KEY_HOME", hold_secs=0.001)
	after = time.time()

	assert before < result2.start_time < result2.end_time < after
	assert result2.key == "KEY_HOME"
	assert isinstance(result2.frame_before, stbt.Frame)
	assert stbt.last_keypress() == result2

	before = time.time()
	with stbt.pressing("KEY_VOLUMEUP") as result3:
	    assert before < result3.start_time
	    assert result3.end_time is None
	    assert result3.key == "KEY_VOLUMEUP"
	    assert isinstance(result3.frame_before, stbt.Frame)
	    assert stbt.last_keypress() == result3
	after = time.time()
	assert result3.start_time < result3.end_time < after
	assert stbt.last_keypress() == result3
	EOF
    stbt run -vv --control=none test.py || fail "Incorrect press() behaviour"
}

test_press_and_wait() {
    # This is a regression test - dut was incorrectly injected into
    # press_and_wait causing failures that our pytest tests didn't find.
    cat > test.py <<-EOF &&
	import stbt_core as stbt
	import threading

	stbt.press("black")
	stbt.wait_until(stbt.is_screen_black)
	
	assert stbt.press_and_wait("white")
	assert not stbt.press_and_wait("white", timeout_secs=1)
	
	stbt.press("ball")
	stbt.wait_for_motion()
	threading.Timer(0.1, lambda: stbt.press("black")).start()
	assert stbt.wait_for_transition_to_end()
	EOF

    stbt run -vv test.py || fail "Incorrect press_and_wait() behaviour"
}
