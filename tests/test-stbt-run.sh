# Run with ./run-tests.sh

test_extra_arguments() {
    cat > test.py <<-EOF
	import sys
	assert sys.argv[1:] == ["a", "b c"]
	EOF
    stbt-run -v test.py a "b c" &&
    stbt-run -v test.py -- a "b c"
}

test_script_accesses_its_path() {
    touch module.py
    cat > test.py <<-EOF
	import module
	print '__file__: ' + __file__
	assert __file__ == "test.py"
	EOF
    stbt-run -v test.py
}

test_stbt_run_return_code_on_test_failure() {
    local ret
    cat > test.py <<-EOF
	wait_for_match("$testdir/videotestsrc-gamut.png", timeout_secs=0)
	EOF
    stbt-run -v test.py
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret"
}

test_stbt_run_return_code_on_precondition_failure() {
    local ret
    cat > test.py <<-EOF
	import stbt
	with stbt.precondition("Wasn't tuned to gamut pattern"):
	    wait_for_match("$testdir/videotestsrc-gamut.png", timeout_secs=0)
	EOF
    stbt-run -v test.py &> test.log
    ret=$?
    [[ $ret == 2 ]] || fail "Unexpected return code $ret"
    assert grep "PreconditionError: Wasn't tuned to gamut pattern" test.log
}
