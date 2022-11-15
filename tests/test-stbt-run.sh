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
	print('__file__: ' + __file__)
	assert __file__ == "test.py"
	EOF
    stbt run -v test.py
}

test_stbt_run_return_code_on_test_failure() {
    local ret
    cat > test.py <<-EOF
	from stbt_core import wait_for_match
	wait_for_match("$testdir/videotestsrc-gamut.png", timeout_secs=0)
	EOF
    stbt run -v test.py
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret"
}

test_stbt_run_return_code_on_precondition_error() {
    local ret
    cat > test.py <<-EOF
	import stbt_core as stbt
	with stbt.as_precondition("Tune to gamut pattern"):
	    stbt.press("gamut")
	    stbt.wait_for_match("$testdir/videotestsrc-gamut.png",
	                        timeout_secs=0)
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

test_that_stbt_run_saves_screenshot_attached_to_exception() {
    cat > test.py <<-EOF
	from stbt_core import press, wait_for_match
	try:
	    wait_for_match(
	        "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=0)
	except MatchTimeout:
	    press("gamut")
	    wait_for_match("$testdir/videotestsrc-gamut.png")
	    raise
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ] &&
    assert stbt match screenshot.png "$testdir/videotestsrc-redblue.png" &&
    ! [ -f thumbnail.jpg ]
}

test_that_stbt_run_saves_screenshot_on_precondition_error() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	with stbt.as_precondition("Impossible precondition"):
	    stbt.wait_for_match(
	        "$testdir/videotestsrc-redblue-flipped.png", timeout_secs=0)
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ] &&
    ! [ -f thumbnail.jpg ]
}

test_that_stbt_run_saves_last_grabbed_screenshot_on_error() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	from time import sleep
	my_frame = stbt.get_frame()
	stbt.save_frame(my_frame, "grabbed-frame.png")
	sleep(0.1)  # Long enough for videotestsrc to produce more frames
	assert False
	EOF
    ! stbt run -v test.py &&
    [ -f screenshot.png ] &&
    ! [ -f thumbnail.jpg ] &&
    $python <<-EOF
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
	    print("%i bottles of beer on the wall" % c)
	    time.sleep(1)
	print("No beer left")
	EOF
    stbt run test.py &
    STBT_PID=$!

    sleep 1
    kill -INT "$STBT_PID"
    wait "$STBT_PID"
    exit_status=$?

    case $exit_status in
        1|130)  cat log | grep -q "No beer left" &&
                fail "Test script should not have completed" ||
            return 0
            ;;
        77) return 77;;
        *) fail "Unexpected return code $exit_status";;
    esac
}

test_that_stbt_run_will_run_a_specific_function() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	def test_that_this_test_is_run():
	    open("touched", "w").close()
	EOF
    stbt run test.py::test_that_this_test_is_run
    [ -e "touched" ] || fail "Test not run"
}

test_that_relative_imports_work_when_stbt_run_runs_a_specific_function() {
    set -x
    mkdir tests
    cat >tests/helpers.py <<-EOF
	def my_helper():
	    print("my_helper() called")
	    open("touched", "w").close()
	EOF
    cat >tests/test.py <<-EOF
	def test_that_this_test_is_run():
	    import helpers
	    helpers.my_helper()
	EOF
    stbt run tests/test.py::test_that_this_test_is_run
    [ -e "touched" ] || fail "Test not run"

    # This test is similar but uses a real relative import
    cat >tests/test_rel.py <<-EOF
	def test_that_this_test_is_run():
	    from .helpers import my_helper
	    my_helper()
	EOF

    # Fails with "ValueError: Attempted relative import in non-package"
    ! stbt run tests/test_rel.py::test_that_this_test_is_run \
         || fail "Relative imports shouldn't work without __init__.py"

    # Now we make it a package and it works again
    touch tests/__init__.py
    stbt run tests/test_rel.py::test_that_this_test_is_run \
         || fail "Relative imports in package should work"

    # And test sub-packages
    mkdir -p tests/subpackage
    touch tests/subpackage/__init__.py
    cat >tests/subpackage/test_subrel.py <<-EOF
	def test_that_this_test_is_run():
	    from ..helpers import my_helper
	    my_helper()
	EOF
    stbt run tests/subpackage/test_subrel.py::test_that_this_test_is_run \
         || fail "Relative imports in package should work"

    # And sub-sub-packages
    mkdir -p tests/subpackage/subsubpackage
    touch tests/subpackage/subsubpackage/__init__.py
    cat >tests/subpackage/subsubpackage/test_subsubrel.py <<-EOF
	def test_that_this_test_is_run():
	    from ...helpers import my_helper
	    my_helper()
	EOF
    stbt run tests/subpackage/subsubpackage/test_subsubrel.py::test_that_this_test_is_run \
         || fail "Relative imports in package should work"
}

test_that_stbt_run_can_print_exceptions_with_unicode_characters() {
    which unbuffer &>/dev/null || skip "unbuffer is not installed"

    cat > test.py <<-EOF
	import sys
	print(sys.argv[1])
	if sys.argv[1] == "raise-unicode":
	    raise RuntimeError(u"Röthlisberger")
	elif sys.argv[1] == "raise-bytes":
	    raise RuntimeError(u"Röthlisberger".encode("utf-8"))
	elif sys.argv[1] == "raise-non-utf8-bytes":
	    # https://www.cl.cam.ac.uk/~mgk25/ucs/examples/UTF-8-test.txt
	    raise RuntimeError(b"\xfe")
	elif sys.argv[1] == "assert-unicode":
	    assert False, u"Röthlisberger"
	elif sys.argv[1] == "assert-bytes":
	    assert False, u"Röthlisberger".encode("utf-8")
	elif sys.argv[1] == "assert-without-message":
	    assert u"Röthlisberger" is None
	EOF

    unicode_test raise-unicode
    unicode_test raise-bytes
    unicode_test raise-non-utf8-bytes
    unicode_test assert-unicode
    unicode_test assert-bytes
    unicode_test assert-without-message
}

unicode_test() {
    echo "unicode_test $1: writing to file"
    stbt run test.py $1 &> $1.log
    assert check_unicode_error $1 $1.log

    echo "unicode_test $1: using unbuffer to simulate interactive use"
    unbuffer bash -c "stbt run test.py $1" &> $1.unbuffer.log
    assert check_unicode_error $1 $1.unbuffer.log
}

check_unicode_error() {
    local scenario=$1 output=$2

    case "$python_version,$scenario" in
        *,raise-unicode|2.7,raise-bytes) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: RuntimeError: Röthlisberger
		Traceback (most recent call last):
		  File ".*/test.py", line .*, in <module>
		    raise RuntimeError(u"Röthlisberger".*)
		RuntimeError: Röthlisberger
		EOF
        3,raise-bytes) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: RuntimeError: b'R.xc3.xb6thlisberger'
		Traceback (most recent call last):
		  File ".*/test.py", line .*, in <module>
		    raise RuntimeError(u"Röthlisberger".encode("utf-8"))
		RuntimeError: b'R.xc3.xb6thlisberger'
		EOF
        # It looks like "RuntimeError: �" but I can't get grep to match it:
        *,raise-non-utf8-bytes) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: RuntimeError:
		Traceback (most recent call last):
		  File ".*/test.py", line .*, in <module>
		    raise RuntimeError(b".xfe")
		RuntimeError:
		EOF
        *,assert-unicode|2.7,assert-bytes) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: AssertionError: Röthlisberger
		Traceback (most recent call last):
		  File ".*/test.py", line .*, in <module>
		    assert False, u"Röthlisberger".*
		AssertionError: Röthlisberger
		EOF
        3,assert-bytes) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: AssertionError: b'R.xc3.xb6thlisberger'
		Traceback (most recent call last):
		  File ".*/test.py", line .*, in <module>
		    assert False, u"Röthlisberger".encode("utf-8")
		AssertionError: b'R.xc3.xb6thlisberger'
		EOF
        *,assert-without-message) cat <<-EOF ;;
		Saved screenshot to 'screenshot.png'.
		FAIL: test.py: AssertionError: assert u"Röthlisberger" is None
		Traceback (most recent call last):
		  File ".*test.py", line .*, in <module>
		    assert u"Röthlisberger" is None
		AssertionError
		EOF
        *) fail "check_unicode_error isn't implemented for $scenario" ;;
    esac |
    while IFS='' read line; do
        grep -q -e "^$line" $output || {
            cat $output;
            fail "Didn't find line: «$line»";
        }
    done
}

test_that_stbt_run_can_print_ioerror() {
    cat > test.py <<-EOF
	open("nonexistent")
	EOF
    ! stbt run test.py &&
    assert_log "FileNotFoundError: [Errno 2] No such file or directory: 'nonexistent'"

    cat > test.py <<-EOF
	open("nönexistent")
	EOF
    ! env LANG=C.UTF-8 stbt run test.py &&
    assert_log "FileNotFoundError: [Errno 2] No such file or directory: 'nönexistent'"
}

test_that_error_control_raises_exception() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("KEY_UP")
	EOF
    ! stbt run -v --control=error test.py &&
    grep -q 'FAIL: test.py: RuntimeError: No remote control configured' log &&

    ! stbt run -v --control="error:My custom error message" test.py &&
    grep -q 'FAIL: test.py: RuntimeError: My custom error message' log
}

test_that_default_control_raises_exception() {
    sed '/^control/ d' config/stbt/stbt.conf | sponge config/stbt/stbt.conf
    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("KEY_UP")
	EOF
    ! stbt run -v test.py &&
    grep -q 'FAIL: test.py: RuntimeError: No remote control configured' log
}

test_that_stbt_run_doesnt_import_unrelated_files() {
    # This is a regression test for a bug where if you import from
    # 'future.moves' (a Python 2/3 compatibility library) it automatically
    # tries to import every python module it finds at the current working
    # directory.
    cat > test.py <<-EOF
	print("This is coming from test.py")
	EOF
    cat > test2.py <<-EOF
	import stbt_core as stbt
	print("OK")
	EOF
    stbt run -v test2.py || fail
    if grep -q "This is coming from test.py" log; then
        fail "test.py was run but I asked for test2.py"
    fi
}
