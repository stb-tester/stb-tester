# Run with ./run-tests.sh

_pytest() {
    PYTHONPATH=$srcdir:$PYTHONPATH pytest-3 -p stbt_run "$@"
}

test_pytest() {
    local ret
    cat > test.py <<-EOF
	from stbt_core import match, wait_until
	
	def test_1():
	    assert True
	
	def test_2():
	    assert wait_until(lambda: match("$testdir/videotestsrc-gamut.png"),
	                      timeout_secs=0)
	EOF
    _pytest -v test.py::test_1
    ret=$?
    [[ $ret == 0 ]] || fail "Unexpected return code $ret"

    _pytest -v test.py::test_2
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret"
    grep -q "AssertionError: assert MatchResult" log \
        || fail "pytest didn't show the failing assert value"
}
