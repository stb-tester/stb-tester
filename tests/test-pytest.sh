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

test_pytest_wait_until_output() {
    cat > test.py <<-EOF
	import functools
	from stbt_core import wait_until
	def test_1():
	    assert True
	    assert 1 == 1
	    assert not wait_until(
	        functools.partial(lambda x: False, x=3), timeout_secs=0.01)
	    assert 2 == 2
	    assert 3 == 3
	EOF
    _pytest -v -rP test.py::test_1 || fail "Should have passed"
    sed -n '/Captured stderr call/,$ p' < log > stderr.log
    if grep -q "assert 1 == 1" stderr.log; then
        fail "wait_until debug shows entire containing function"
    fi
}
