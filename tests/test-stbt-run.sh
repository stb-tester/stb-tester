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

test_that_stbt_run_treats_failing_assertions_as_test_errors() {
    local ret
    cat > test.py <<-EOF
	assert False, "My assertion"
	EOF
    stbt run -v test.py &> test.log
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret (expected 2)"
    assert grep -q "FAIL: test.py: AssertionError: My assertion" test.log
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

test_that_stbt_run_exits_on_ctrl_c() {
    # Enable job control, otherwise bash prevents sigint to background command.
    set -m

    cat > test.py <<-EOF
	import sys, time, gi
	from gi.repository import GLib
	
	for c in range(5, 0, -1):
	    print "%i bottles of beer on the wall" % c
	    time.sleep(1)
	print "No beer left"
	
	if not hasattr(GLib.MainLoop, "new"):
	    print "Ignore test failure on PyGObject <3.7.2 (e.g. Ubuntu 12.04)"
	    sys.exit(77)  # skip
	EOF
    stbt run test.py &
    STBT_PID=$!

    sleep 1
    kill -INT "$STBT_PID"
    wait "$STBT_PID"
    exit_status=$?

    case $exit_status in
        1)  cat log | grep -q "No beer left" &&
                fail "Test script should not have completed" ||
            return 0
            ;;
        77) return 77;;
        *) fail "Unexpected return code $exit_status";;
    esac
}
