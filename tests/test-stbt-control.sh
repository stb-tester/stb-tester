test_that_stbt_control_sends_a_single_key() {
    set_config global.verbose 1 &&
    stbt control --control none MENU &&
    cat log | grep -q 'NullControl: Ignoring request to press "MENU"'
}
