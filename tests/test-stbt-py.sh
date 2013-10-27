# Run with ./run-tests.sh

test_that_invalid_control_doesnt_hang() {
    touch test.py
    timeout 10 stbt-run -v --control asdf test.py
    local ret=$?
    [ $ret -ne $timedout ] || fail "'stbt-run --control asdf' timed out"
}

test_invalid_source_pipeline() {
    touch test.py
    stbt-run -v --source-pipeline viddily-boo test.py &> stbt.log
    tail -n1 stbt.log | grep -q 'no element "viddily-boo"' ||
        fail "The last error message in '$scratchdir/stbt.log' wasn't the" \
            "expected 'no element \"viddily-boo\"'"
}

test_get_frame_and_save_frame() {
    cat > get-screenshot.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue.png", consecutive_matches=24)
	press("gamut")
	wait_for_match(
	    "$testdir/videotestsrc-gamut.png", consecutive_matches=24)
	save_frame(get_frame(), "gamut.png")
	EOF
    stbt-run -v get-screenshot.py
    [ -f gamut.png ] ||
        fail "Screenshot '$scratchdir/gamut.png' wasn't created"

    cat > match-screenshot.py <<-EOF
	press("gamut")
	# confirm_threshold accounts for match rectangle in the screenshot.
	wait_for_match("gamut.png",
	               match_parameters=MatchParameters(confirm_threshold=0.7))
	EOF
    stbt-run -v match-screenshot.py
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
    stbt-run -v test.py
}

test_that_frames_returns_at_least_one_frame() {
    cat > test.py <<-EOF
	import stbt
	stbt.frames(timeout_secs=0).next()
	stbt.frames(timeout_secs=0).next()
	EOF
    stbt-run -v test.py
}

test_that_frames_doesnt_time_out() {
    cat > test.py <<-EOF
	import stbt
	for _ in stbt.frames():
	    pass
	EOF
    timeout 12 stbt-run -v test.py
    local ret=$?
    [ $ret -eq $timedout ] || fail "Unexpected exit status '$ret'"
}

test_that_frames_raises_NoVideo() {
    cat > test.py <<-EOF
	import stbt
	for _ in stbt.frames():
	    pass
	EOF
    stbt-run -v \
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
	
	def is_black_screen(img):
	    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	    _, img = cv2.threshold(img, 10, 255, cv2.THRESH_BINARY)
	    _, maxVal, _, _ = cv2.minMaxLoc(img)
	    return maxVal == 0
	
	threading.Thread(target=presser).start()
	
	frames = stbt.frames(timeout_secs=10)
	for frame, timestamp in frames:
	    black = is_black_screen(frame)
	    print "%s: %s" % (timestamp, black)
	    if black:
	        break
	assert black, "Failed to find black screen"
	for frame, timestamp in frames:
	    black = is_black_screen(frame)
	    print "%s: %s" % (timestamp, black)
	    if not black:
	        break
	assert not black, "Failed to find non-black screen"
	EOF
    stbt-run -v test.py
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
	frames = stbt.frames()  # Drop reference to old `frames`; should be GCd.
	frame2 = frames.next()
	frames3 = stbt.frames()
	frame3 = frames3.next()  # old `frames` still holds lock
	EOF
    timeout 10 stbt-run -v test.py &&

    cat > test2.py <<-EOF
EOF
}

test_that_video_index_is_written_on_eos() {
    which webminspector.py &>/dev/null || {
        echo "webminspector.py not found; skipping this test." >&2
        echo "See http://git.chromium.org/gitweb/?p=webm/webminspector.git" >&2
        return 0
    }

    [ $(uname) = Darwin ] && {
        echo "Skipping this test because vp8enc/webmmux don't work on OS X" >&2
        return 0
    }

    cat > test.py <<-EOF &&
	import time
	time.sleep(5)
	EOF
    stbt-run -v \
        --sink-pipeline \
            "queue ! vp8enc speed=7 ! webmmux ! filesink location=video.webm" \
        test.py &&
    webminspector.py video.webm &> webminspector.log &&
    grep "Cue Point" webminspector.log || {
      cat webminspector.log
      fail "Didn't find 'Cue Point' in $scratchdir/webminspector.log"
    }
}

test_save_video() {
    [ $(uname) = Darwin ] && {
        echo "Skipping this test because vp8enc/webmmux don't work on OS X" >&2
        return 0
    }

    cat > record.py <<-EOF &&
	import time
	time.sleep(2)
	EOF
    sed -e 's/save_video =.*/save_video = video.webm/' \
        "$testdir/stbt.conf" > stbt.conf &&
    STBT_CONFIG_FILE="$scratchdir/stbt.conf" stbt-run -v record.py &&
    cat > test.py <<-EOF &&
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF
    stbt-run -v --control none \
        --source-pipeline 'filesrc location=video.webm ! decodebin' \
        test.py
}

test_that_verbosity_level_is_read_from_config_file() {
    sed 's/verbose = 0/verbose = 2/' "$testdir/stbt.conf" > stbt.conf &&
    touch test.py &&
    STBT_CONFIG_FILE="$PWD/stbt.conf" stbt-run test.py &&
    cat log | grep "verbose: 2"
}

test_that_verbose_command_line_argument_overrides_config_file() {
    sed 's/verbose = 0/verbose = 2/' "$testdir/stbt.conf" > stbt.conf &&
    touch test.py &&
    STBT_CONFIG_FILE="$PWD/stbt.conf" stbt-run -v test.py &&
    cat log | grep "verbose: 1"
}

test_that_restart_source_option_is_read() {
    cat > test.py <<-EOF &&
	import stbt
	print "value: %s" % stbt._display.restart_source_enabled
	EOF
    # Read from the command line
    stbt-run -v --restart-source --control none test.py &&
    cat log | grep "restart_source: True" &&
    cat log | grep "value: True" &&
    echo > log &&
    # Read from the config file
    sed 's/restart_source = .*/restart_source = True/' \
        "$testdir/stbt.conf" > stbt.conf &&
    STBT_CONFIG_FILE="$PWD/stbt.conf" stbt-run -v --control none test.py &&
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

    stbt-run -v \
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
    stbt-run -v --control none \
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

    stbt-run -v --control none \
        --source-pipeline 'videotestsrc is-live=true pattern=black' \
        --sink-pipeline 'gdppay ! filesink location=fifo sync=false' \
        draw-text.py &
    trap 'kill $!; rm fifo' EXIT

    stbt-run -v --control none \
        --source-pipeline 'filesrc location=fifo ! gdpdepay' \
        verify-draw-text.py
}

test_load_image() {
    cat > load_image1.py <<-EOF &&
	import stbt
	assert stbt.load_image('$testdir/black.png') is not None
	EOF
    stbt-run -v load_image1.py ||
    fail "load_image failed to load real image"

    cat > load_image2.py <<-EOF &&
	import stbt
	try:
	    stbt.load_image("$testdir/invalid-black.png")
	except stbt.UITestError as e:
	    assert 'No such file' in str(e)
	EOF
    stbt-run -v load_image2.py ||
    fail "load_image didn't raise 'No such file' for non-existent file"

    cat > load_image3.py <<-EOF &&
	import stbt
	try:
	    stbt.load_image("$testdir/test-stbt-py.sh")
	except stbt.UITestError as e:
	    assert 'Failed to load image' in str(e)
	EOF
    stbt-run -v load_image3.py ||
    fail "load_image didn't raise 'Failed to load image' for non-image file"
}

test_match_template() {
    cat > match_template1.py <<-EOF &&
	import stbt
	im = stbt.load_image("$testdir/black.png")
	matched, pos, fpc = stbt.match_template(im, im)
	assert matched == True
	assert pos == (0, 0)
	assert str(fpc).startswith("0.999999")
	EOF
    stbt-run -v match_template1.py ||
    fail "match_template didn't correctly match an image to itself"

    cat > match_template2.py <<-EOF &&
	import stbt
	im1 = stbt.load_image("$testdir/known-fail-source.png")
	im2 = stbt.load_image("$testdir/known-fail-template.png")
	matched, pos, fpc = stbt.match_template(im1, im2)
	assert matched == True
	assert pos == (9, 72)
	assert str(fpc).startswith("0.834914")
	EOF
    stbt-run -v match_template2.py ||
    fail "match_template didn't get false positive with default parameters"

    # Note that pos/fpc are the same because they are from the *first pass*
    cat > match_template3.py <<-EOF &&
	import stbt
	im1 = stbt.load_image("$testdir/known-fail-source.png")
	im2 = stbt.load_image("$testdir/known-fail-template.png")
	mp = stbt.MatchParameters(confirm_method="normed-absdiff")
	matched, pos, fpc = stbt.match_template(im1, im2, match_parameters=mp)
	assert matched == False
	assert pos == (9, 72)
	assert str(fpc).startswith("0.834914")
	EOF
    stbt-run -v match_template3.py ||
    fail "match_template didn't get true negative with non-default parameters"
}
