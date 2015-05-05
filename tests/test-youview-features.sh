skip_if_uitests_is_not_in_pythonpath() {
    if ! python -c 'import common' &>/dev/null; then
        skip "youviewtv/uitests is not in PYTHONPATH"
    fi
}

test_survive_failure_as_decorator_handles_multiple_exceptions() {
    skip_if_uitests_is_not_in_pythonpath

    cat > "$scratchdir/test.py" <<-EOF
	import stbt, common
	@common.SurviveFailure()
	def fail():
	    raise stbt.UITestFailure()
	fail()
	fail()
	fail()
	EOF
    ! stbt run -v "$scratchdir/test.py" &> test.log || fail "Test didn't fail"
    local expected=3
    local actual=$(grep -c "stbt.UITestFailure" test.log)
    [[ ${actual} -eq ${expected} ]] ||
        fail "Expected ${expected} exceptions, got ${actual}"
}

test_survive_failure_as_context_manager_handles_multiple_exceptions() {
    skip_if_uitests_is_not_in_pythonpath

    cat > "$scratchdir/test.py" <<-EOF
	import stbt, common
	def fail():
	    with common.SurviveFailure('foo'):
	        raise stbt.UITestFailure()
	fail()
	fail()
	fail()
	EOF
    ! stbt run -v "$scratchdir/test.py" &> test.log || fail "Test didn't fail"
    local expected=3
    local actual=$(grep -c "stbt.UITestFailure" test.log)
    [[ ${actual} -eq ${expected} ]] ||
        fail "Expected ${expected} exceptions, got ${actual}"
}

test_survive_failure_as_decorator_prints_exception() {
    skip_if_uitests_is_not_in_pythonpath

    cat > "$scratchdir/test.py" <<-EOF
	import stbt, common
	@common.SurviveFailure()
	def fail1():
	    raise stbt.UITestFailure()
	@common.SurviveFailure()
	def fail2():
	    raise stbt.UITestFailure("Message")
	fail1()
	fail2()
	EOF
    ! stbt run -v "$scratchdir/test.py" &> test.log || fail "Test didn't fail"
    assert grep "fail1: UITestFailure:" test.log
    assert grep "fail2: UITestFailure: Message" test.log
}

test_survive_failure_as_context_manager_prints_exception() {
    skip_if_uitests_is_not_in_pythonpath

    cat > "$scratchdir/test.py" <<-EOF
	import stbt, common
	def fail1():
	    with common.SurviveFailure('failure 1'):
	        raise stbt.UITestFailure()
	def fail2():
	    with common.SurviveFailure('failure 2'):
	        raise stbt.UITestFailure("Message")
	fail1()
	fail2()
	EOF
    ! stbt run -v "$scratchdir/test.py" &> test.log || fail "Test didn't fail"
    assert grep "^FAIL: failure 1 (1): UITestFailure: $" test.log
    assert grep "^FAIL: failure 2 (1): UITestFailure: Message$" test.log
}

test_survive_failure_registers_manual_failure_reason() {
    skip_if_uitests_is_not_in_pythonpath

    cat > "$scratchdir/test.py" <<-EOF
	import classify_tools, common, stbt
	with common.SurviveFailure('Survive one failure'):
	    with classify_tools.classify_failure_as('One failure'):
	        raise stbt.UITestFailure()
	with common.SurviveFailure('Survive other failure'):
	    with classify_tools.classify_failure_as('Other failure'):
	        raise stbt.UITestFailure()
	EOF
    ! stbt run -v "$scratchdir/test.py" || fail "Test didn't fail"

    assert grep "One failure" "$scratchdir/failure-reason.manual"
    assert grep "Other failure" "$scratchdir/failure-reason.manual"
    assert grep "Failure count	2" "$scratchdir/extra-columns"
}

test_survive_failure_important_failure_overrides_ignored_failure() {
    skip_if_uitests_is_not_in_pythonpath

    cat > test.py <<-EOF
	import common, stbt
	with common.SurviveFailure('something'):
	    raise stbt.UITestFailure('boring failure')
	raise stbt.UITestFailure('interesting failure')
	EOF
    stbt run -v --control none test.py &> test.log
    ret=$?
    [[ $ret == 1 ]] || fail "Unexpected return code $ret"
    assert grep -E "FAIL:.*interesting failure" test.log
}
