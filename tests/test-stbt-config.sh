# Run with ./run-tests.sh

test_that_stbt_config_reads_from_STBT_CONFIG_FILE() {
    [ "$(stbt-config test_key)" = "this is a test value" ]
}

test_that_stbt_config_tool_section_overrides_global_section() {
    [ "$(stbt-config special test_key)" = "overrides the global value" ]
}

test_that_stbt_config_searches_global_section_if_key_not_in_tool_section() {
    [ "$(stbt-config special control)" = "test" ]
}

test_that_stbt_config_returns_failure_on_key_not_found() {
    ! stbt-config no_such_key &&
    ! stbt-config no_such_section test_key
}
