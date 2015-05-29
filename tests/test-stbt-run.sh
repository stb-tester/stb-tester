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
    [[ $ret == 2 ]] || fail "Unexpected return code $ret (expected 2)"
    assert grep -q "FAIL: test.py: AssertionError: My assertion" test.log
}

test_that_stbt_run_prints_assert_statement_if_no_assertion_message_given() {
    cat > test.py <<-EOF
	assert 1 + 1 == 3
	EOF
    stbt run -v test.py &> test.log
    assert grep -q "FAIL: test.py: AssertionError: assert 1 + 1 == 3" test.log
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

test_that_stbt_run_will_run_a_specific_function() {
    cat > test.py <<-EOF
	import stbt
	def test_that_this_test_is_run():
	    open("touched", "w").close()
	EOF
    stbt run test.py::test_that_this_test_is_run
    [ -e "touched" ] || fail "Test not run"
}

test_that_relative_imports_work_when_stbt_run_runs_a_specific_function() {
    mkdir tests
    cat >tests/helpers.py <<-EOF
	def my_helper():
	    open("touched", "w").close()
	EOF
    cat >tests/test.py <<-EOF
	def test_that_this_test_is_run():
	    import helpers
	    helpers.my_helper()
	EOF
    stbt run tests/test.py::test_that_this_test_is_run
    [ -e "touched" ] || fail "Test not run"
}

test_that_registered_failures_are_reported_on_success() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id-1', 'my description-1')
	stbt.push_test_failure('my-bug-id-2', 'my description-2')
	print "End of test reached."
	EOF
    stbt run -v test.py &> test.log
    assert grep -q "Failure: (@.*) my-bug-id-1 - my description-1" test.log
    assert grep -q "Failure: (@.*) my-bug-id-2 - my description-2" test.log
    assert grep -q "End of test reached." test.log
}

test_that_no_registered_failures_on_success_has_no_effect() {
    cat > test.py <<-EOF
	print "Everything worked! Isn't that great?"
	EOF
    stbt run -v test.py &> test.log
    exit_status=${?}
    assert [ ${exit_status} -eq 0 ]
    assert grep -qv "Failure (@.*)" test.log
}

test_that_registered_failures_determine_exit_status_on_success() {
    cat > test_1.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id', 'my description')
	EOF
    stbt run -v test_1.py
    exit_status=${?}
    assert [ ${exit_status} -eq 1 ]

    cat > test_2.py <<-EOF
	import stbt
	stbt.push_test_error('my-bug-id', 'my description')
	EOF
    stbt run -v test_2.py
    exit_status=${?}
    assert [ ${exit_status} -eq 2 ]
}

test_that_one_registered_failure_determines_exception_raised_on_success() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id', 'my description')
	EOF
    stbt run -v test.py &> test.log
    assert grep -q \
        "FAIL: test.py: UITestFailure: "\
        "Encountered a single failure during test execution." test.log
}

test_that_one_registered_failure_with_exception_determines_exception_raised_on_success() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure(
	    'my-bug-id', 'my description', exception=RuntimeError("It didn't work"))
	EOF
    stbt run -v test.py &> test.log
    assert grep -q \
        "FAIL: test.py: RuntimeError: It didn't work" test.log
}

test_that_multiple_registered_failures_determine_exit_status_on_success() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id', 'my description')
	stbt.push_test_error('my-bug-id', 'my description')
	EOF
    stbt run -v test.py
    exit_status=${?}
    assert [ ${exit_status} -eq 1 ]
}

test_that_registered_failures_are_reported_on_failure() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id-1', 'my description-1')
	stbt.push_test_failure('my-bug-id-2', 'my description-2')
	raise stbt.UITestFailure("Unanticipated failure")
	EOF
    stbt run -v test.py &> test.log
    assert grep -q "Failure: (@.*) my-bug-id-1 - my description-1" test.log
    assert grep -q "Failure: (@.*) my-bug-id-2 - my description-2" test.log
}

test_that_registered_failures_dont_determine_exit_status_on_failure() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_error('my-bug-id', 'my-description')
	raise stbt.UITestFailure("Unanticipated failure")
	EOF
    stbt run -v test.py &> test.log
    exit_status=${?}
    assert [ ${exit_status} -eq 1 ]
}

test_that_registered_failures_dont_determine_exception_raised_on_failure() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('my-bug-id', 'my-description')
	raise stbt.UITestFailure("Unanticipated failure")
	EOF
    stbt run -v test.py &> test.log
    assert grep -q "FAIL: test.py: "\
        "UITestFailure: Unanticipated failure" test.log
}

test_that_registered_failures_without_screenshots_grab_from_live() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure('MYBUG-ABC', 'bad thing happened')
	EOF
    stbt run -v test.py
    [ -f MYBUG-ABC.png ] ||
    fail "Screenshots not found. Directory contains: $(ls -1)"
}

test_that_registered_failures_with_screenshots_are_saved() {
    cat > test.py <<-EOF
	import stbt
	stbt.push_test_failure(
	    'MYBUG-123', 'bad thing happened', screenshot=stbt.get_frame())
	stbt.push_test_failure(
	    'MYBUG-456', 'other bad thing happened', screenshot=stbt.get_frame())
	raise stbt.MatchTimeout(stbt.get_frame(), 'nothing', 0)
	EOF
    stbt run -v test.py
    [ -f MYBUG-123.png ] &&
    [ -f MYBUG-456.png ] &&
    [ -f screenshot.png ] ||
    fail "Screenshots not found. Directory contains: $(ls -1)"
}
