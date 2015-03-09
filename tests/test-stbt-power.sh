# Run with ./run-tests.sh

test_that_stbt_power_status_prints_ON_by_default() {
    [ "$(stbt power status)" = "ON" ] || fail
}

test_that_stbt_power_status_on_and_off_fail_by_default() {
    stbt power on || fail "Power should be always on if there is no outlet"
    ! stbt power off || fail "Cannot switch off if there is no outlet"
}

test_that_selected_power_controller_comes_from_command_line_then_config() {
    echo 0 >power-status
    echo 0 >power-status2
    set_config global.power_outlet "file:$PWD/power-status"

    stbt power --power-outlet=file:$PWD/power-status2 on
    [ "$(< power-status2)" = "1" ] || fail "Wrong power outlet selected"

    stbt power on
    [ "$(< power-status)" = "1" ] || fail "Wrong power outlet selected"
}

test_that_stbt_power_status_prints_status() {
    set_config global.power_outlet "file:$PWD/power-status"

    [ "$(stbt power status)" = "ON" ] || fail
    stbt power off
    [ "$(stbt power status)" = "OFF" ] || fail
    stbt power on
    [ "$(stbt power status)" = "ON" ] || fail
}

test_stbt_power_shell_fallback() {
    for cmd in on off status; do
        stbt power --power-outlet=testfallback:a:1 "$cmd" \
            || fail "Shell fallback failed"
    done
}
