# Run with ./run-tests.sh

test_that_invalid_control_doesnt_hang() {
    touch "$scratchdir/test.py"
    timeout 10 stbt-run --control asdf "$scratchdir/test.py"
    local ret=$?
    [ $ret -ne $timedout ] || fail "'stbt-run --control asdf' timed out"
}

test_invalid_source_pipeline() {
    touch "$scratchdir/test.py"
    stbt-run --source-pipeline viddily-boo "$scratchdir/test.py" \
        &> "$scratchdir/stbt.log"
    tail -n1 "$scratchdir/stbt.log" | grep -q 'no element "viddily-boo"' ||
        fail "The last error message in '$scratchdir/stbt.log' wasn't the" \
            "expected 'no element \"viddily-boo\"'"
}

test_get_frame_and_save_frame() {
    cat > "$scratchdir/get-screenshot.py" <<-EOF
	wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
	press("15")
	wait_for_match("videotestsrc-gamut.png", consecutive_matches=24)
	save_frame(get_frame(), "$scratchdir/gamut.png")
	EOF
    stbt-run -v "$scratchdir/get-screenshot.py"
    [ -f "$scratchdir/gamut.png" ] ||
        fail "Screenshot '$scratchdir/gamut.png' wasn't created"

    cat > "$scratchdir/match-screenshot.py" <<-EOF
	press("15")
	# confirm_threshold accounts for match rectangle in the screenshot.
	wait_for_match("$scratchdir/gamut.png",
	               match_parameters=MatchParameters(confirm_threshold=0.7))
	EOF
    stbt-run -v "$scratchdir/match-screenshot.py"
}

test_get_config() {
    cat > "$scratchdir/test.py" <<-EOF
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
    stbt-run "$scratchdir/test.py"
}

test_that_frames_returns_at_least_one_frame() {
    cat > "$scratchdir/test.py" <<-EOF
	import stbt
	stbt._display.frames(timeout_secs=0).next()
	stbt._display.frames(timeout_secs=0).next()
	EOF
    stbt-run "$scratchdir/test.py"
}

test_that_frames_doesnt_time_out() {
    cat > "$scratchdir/test.py" <<-EOF
	import stbt
	for _ in stbt._display.frames():
	    pass
	EOF
    timeout 12 stbt-run "$scratchdir/test.py"
    local ret=$?
    [ $ret -eq $timedout ] || fail "Unexpected exit status '$ret'"
}

test_that_frames_raises_NoVideo() {
    cat > "$scratchdir/test.py" <<-EOF
	import stbt
	for _ in stbt._display.frames():
	    pass
	EOF
    ! stbt-run --source-pipeline "videotestsrc num-buffers=1" \
            "$scratchdir/test.py" &> "$scratchdir/stbt-run.log" &&
    grep -q NoVideo "$scratchdir/stbt-run.log" ||
    fail "'NoVideo' exception wasn't raised in $scratchdir/stbt-run.log"
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

    cd "$scratchdir" &&
    cat > test.py <<-EOF &&
	import time
	time.sleep(2)
	EOF
    stbt-run -v \
        --sink-pipeline \
            "queue ! vp8enc speed=7 ! webmmux ! filesink location=video.webm" \
        test.py &&
    webminspector.py video.webm &> webminspector.log &&
    grep "Cue Point" webminspector.log ||
    fail "Didn't find 'Cue Point' in $scratchdir/webminspector.log"
}

test_save_video() {
    [ $(uname) = Darwin ] && {
        echo "Skipping this test because vp8enc/webmmux don't work on OS X" >&2
        return 0
    }

    cd "$scratchdir" &&
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
