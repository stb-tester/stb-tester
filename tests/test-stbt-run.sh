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

test_that_stbt_run_saves_last_grabbed_screenshot_on_error() {
    cat > test.py <<-EOF
	import stbt
	from time import sleep
	my_frame = stbt.get_frame()
	stbt.save_frame(my_frame, "grabbed-frame.png")
	sleep(0.1)  # Long enough for videotestsrc to produce more frames
	assert False
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ] &&
    python <<-EOF
	import cv2, numpy
	ss = cv2.imread('screenshot.png')
	gf = cv2.imread('grabbed-frame.png')
	assert ss is not None and gf is not None
	assert numpy.all(ss == gf)
	EOF
}

test_that_stbt_run_exits_on_ctrl_c() {
    # Enable job control, otherwise bash prevents sigint to background command.
    set -m

    cat > test.py <<-EOF
	import sys, time, gi
	gi.require_version("Gst", "1.0")
	from gi.repository import GLib
	
	for c in range(5, 0, -1):
	    print "%i bottles of beer on the wall" % c
	    time.sleep(1)
	print "No beer left"
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

state_printer() {
    cat > state_printer.py <<-EOF
		import json
		import sys
		from _stbt import state_watch
		data = {}
		sr = state_watch.StateReceiver(data)
		for line in sys.stdin:
		    sr.write(line)
		    print json.dumps(data, sort_keys=True)
		EOF
    PYTHONPATH=$srcdir python state_printer.py
}

run_state_test() {
    cat > test.py <<-EOF &&
	stbt.wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF

    cat > expected_states <<-EOF
		{"test_run": {"current_line": {}, "test_case": {"file": "test.py", "function": "", "line": 1, "name": "test.py"}}}
		{"test_run": {"current_line": {"file": "$PWD/test.py", "line": 1}, "test_case": {"file": "test.py", "function": "", "line": 1, "name": "test.py"}}}
		{"test_run": {}}
		EOF

    stbt run "$@" test.py || fail "Test failed"
}

test_that_stbt_run_tracing_is_written_to_file() {
    run_state_test --save-trace=trace.jsonl.xz || fail "Test failed"
    [ -e "trace.jsonl.xz" ] || fail "Trace not written"
    xzcat "trace.jsonl.xz" | grep -q "state_change" || fail "state_change not written"
    diff expected_states <(xzcat "trace.jsonl.xz" | state_printer)
}

test_that_stbt_run_tracing_is_written_to_socket() {
    export STBT_TRACING_SOCKET=$PWD/trace-socket
    socat UNIX-LISTEN:$STBT_TRACING_SOCKET,fork OPEN:trace.jsonl,creat,append &
    SOCAT_PID=$!
    sleep 1

    run_state_test || fail "Test failed"
    kill "$SOCAT_PID"
    grep -q "state_change" "trace.jsonl" || fail "state_change not written"
    diff expected_states <(state_printer <"trace.jsonl") || fail "Wrong states"
}

assert_correct_unicode_error() {
    cat >expected.log <<-EOF
		FAIL: test.py: AssertionError: ü
		Traceback (most recent call last):
		  File ".../stbt-run", line ..., in <module>
		    execfile(_filename)
		  File "...", line 2, in <module>
		    assert False, $u"ü"
		AssertionError: ü
		EOF
    diff -u <(grep -v -e File expected.log) \
            <(grep -v -e 'libdc1394 error: Failed to initialize libdc1394' \
                      -e File mylog) || fail
}

test_that_stbt_run_can_print_exceptions_with_unicode_characters() {
    which unbuffer &>/dev/null || skip "unbuffer is not installed"

    cat > test.py <<-EOF
	# coding: utf-8
	assert False, u"ü"
	EOF

    stbt run test.py &> mylog
    u="u" assert_correct_unicode_error

    # We use unbuffer here to provide a tty to `stbt run` to simulate
    # interactive use.
    LANG=C.UTF-8 unbuffer bash -c 'stbt run test.py'
    u="u" assert_correct_unicode_error
}

test_that_stbt_run_can_print_exceptions_with_encoded_utf8_string() {
    which unbuffer &>/dev/null || skip "unbuffer is not installed"

    cat > test.py <<-EOF
	# coding: utf-8
	assert False, "ü"
	EOF

    stbt run test.py &> mylog
    assert_correct_unicode_error

    # We use unbuffer here to provide a tty to `stbt run` to simulate
    # interactive use.
    LANG=C.UTF-8 unbuffer bash -c 'stbt run test.py'
    assert_correct_unicode_error
}
