# Tests the self-test framework and the helper functions in utils.sh used by
# the self-tests. Run with ./run-tests.sh

test_assert() {
    ( assert true ) || fail "'assert true' failed"
    ! ( assert ! true ) || fail "'assert ! true' didn't fail"
    ! ( assert false ) || fail "'assert false' didn't fail"
    ( assert ! false ) || fail "'assert ! false' failed"
}

test_killtree() {
    cat > killtree-$$-test1.sh <<-EOF
	sh killtree-$$-test2.sh
	EOF
    cat > killtree-$$-test2.sh <<-EOF
	sh killtree-$$-test3.sh
	EOF
    cat > killtree-$$-test3.sh <<-EOF
	sleep 60
	EOF

    waitfor() { while ! ps -f | grep -v grep | grep "$1"; do sleep 0.1; done; }

    sh killtree-$$-test1.sh &
    pid=$!
    waitfor killtree-$$-test3.sh
    killtree $!
    ps -f
    ! ps -f | grep -v grep | grep -q killtree-$$-test3.sh ||
    fail "child process 'killtree-$$-test3.sh' still running"
}

test_that_run_tests_isnt_affected_by_user_config_file() {
    cat > user.conf <<-EOF
	[global]
	test_key = this is overridden by the user's config
	EOF
    export STBT_CONFIG_FILE=$(pwd)/user.conf
    "$testdir"/run-tests.sh -i _test_that_run_tests_isnt_affected_by_user_config_file
}
_test_that_run_tests_isnt_affected_by_user_config_file() {
    assert [ "$(stbt config global.test_key)" == "this is a test value" ]
}
