# Run with ./run-tests.sh

test_extra_arguments() {
    cat > test.py <<-EOF
	import sys
	assert sys.argv[1:] == ["a", "b c"]
	EOF
    stbt run -v test.py a "b c" &&
    stbt run -v test.py -- a "b c"
}

test_that_optional_arguments_are_passed_through_to_test_script() {
    cat > test.py <<-EOF
	import sys
	assert sys.argv[1:] == ['--option', '--source-pipeline=not_real']
	EOF
    stbt run -v test.py --option --source-pipeline=not_real
}

test_script_accesses_its_path() {
    touch module.py
    cat > test.py <<-EOF
	import module
	print '__file__: ' + __file__
	assert __file__ == "test.py"
	EOF
    stbt run -v test.py
}

test_stbt_run_return_code_on_test_failure() {
    local ret
    cat > test.py <<-EOF
	wait_for_match("$testdir/videotestsrc-gamut.png", timeout_secs=0)
	EOF
    stbt run -v test.py
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret"
}

test_stbt_run_return_code_on_precondition_error() {
    local ret
    cat > test.py <<-EOF
	import stbt
	with stbt.as_precondition("Tune to gamut pattern"):
	    press("gamut")
	    wait_for_match("$testdir/videotestsrc-gamut.png", timeout_secs=0)
	EOF
    stbt run -v --control none test.py &> test.log
    ret=$?
    [[ $ret == 2 ]] || fail "Unexpected return code $ret"
    assert grep \
        "PreconditionError: Didn't meet precondition 'Tune to gamut pattern'" \
        test.log
}

test_that_stbt_run_saves_screenshot_on_match_timeout() {
    cat > test.py <<-EOF
	wait_for_match(
	    "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=0)
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ]
}

test_that_stbt_run_saves_screenshot_on_precondition_error() {
    cat > test.py <<-EOF
	import stbt
	with stbt.as_precondition("Impossible precondition"):
	    wait_for_match(
	        "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=0)
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ]
}

test_that_stbt_run_saves_gst_debug_to_file_when_configured() {
    cat > test.py <<-EOF
	import time
	time.sleep(1)
	EOF

    sed -e 's/gst_debug =/gst_debug=videotestsrc:5/' \
        "$testdir/stbt.conf" > gst-debug.conf
    STBT_CONFIG_FILE=gst-debug.conf stbt run -v test.py
    [ -f stbt-gst-debug.log ]
}

test_that_stbt_run_doesnt_save_gst_debug_to_file_when_not_configured() {
    cat > test.py <<-EOF
	import time
	time.sleep(1)
	EOF

    stbt run -v test.py
    [ ! -f stbt-gst-debug.log ]
}
