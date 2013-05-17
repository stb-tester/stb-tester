test_that_stbt_control_sends_a_single_key() {
    stbt-control --control none MENU &&
    cat "$scratchdir/log" | grep 'NullRemote: Ignoring request to press "MENU"'
}

test_stbt_control_unit_tests() {
    # Workaround for https://github.com/nose-devs/nose/issues/49
    cp ../stbt-control "$scratchdir/stbt-control.py"
    PYTHONPATH=.. nosetests --with-doctest -v "$scratchdir/stbt-control.py"
}
