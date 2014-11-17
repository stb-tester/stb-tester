# Run with ./run-tests.sh

test_that_stbt_config_reads_from_one_STBT_CONFIG_FILE() {
    cat >test-stbt.conf <<-EOF
	[global]
	another_test_key = this is a test value
	EOF
    export STBT_CONFIG_FILE=$PWD/test-stbt.conf &&
    [ "$(stbt config global.another_test_key)" = "this is a test value" ]
}

test_that_stbt_config_reads_from_multiple_STBT_CONFIG_FILEs() {
    cat >test-stbt-1.conf <<-EOF
	[global]
	one_test_key = this is the overridden test value
	another_test_key = this is another test value
	EOF
    cat >test-stbt-2.conf <<-EOF
	[global]
	one_test_key = this is the final test value
	EOF
    export STBT_CONFIG_FILE=$PWD/test-stbt-2.conf:$PWD/test-stbt-1.conf &&
    [ "$(stbt config global.one_test_key)" = "this is the final test value" ] &&
    [ "$(stbt config global.another_test_key)" = "this is another test value" ]
}

test_that_stbt_config_searches_in_specified_section() {
    [ "$(stbt config special.test_key)" = "not the global value" ]
}

test_that_stbt_config_returns_failure_on_key_not_found() {
    ! stbt config global.no_such_key &&
    ! stbt config no_such_section.test_key &&
    ! stbt config not_special.section
}
