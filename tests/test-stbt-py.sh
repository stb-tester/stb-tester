# Run with ./run-tests.sh

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
