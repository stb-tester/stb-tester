test_that_stbt_control_sends_a_single_key() {
    set_config global.verbose 1 &&
    stbt control --control none MENU &&
    cat log | grep -q 'NullRemote: Ignoring request to press "MENU"'
}

validate_stbt_record_control_recorder() {
    which expect &>/dev/null || skip "expect is not installed"
    control_uri=$1

    cat > test.expect <<-EOF &&
	set stty_init "rows 50 cols 80"
	spawn stbt record --control-recorder=$control_uri
	expect "stbt-control.keymap"
	send "f"
	sleep 1
	send "a"
	sleep 1
	send "0"
	sleep 1
	send "q"
	expect eof
	# Exit status -- see http://stackoverflow.com/questions/3299502/
	catch wait result
	exit [lindex \$result 3]
	EOF
    expect test.expect &&

    cat > expected <<-EOF &&
	import stbt
	
	
	def test_that_WRITE_TESTCASE_DESCRIPTION_HERE():
	    stbt.press('gamut')
	    stbt.wait_for_match('0001-gamut-complete.png')
	    stbt.press('checkers-8')
	    stbt.wait_for_match('0002-checkers-8-complete.png')
	    stbt.press('smpte')
	    stbt.wait_for_match('0003-smpte-complete.png')
	EOF
    diff -u expected test.py
}

test_stbt_control_as_stbt_record_control_recorder__explicit_keymap() {
    validate_stbt_record_control_recorder \
        stbt-control:$testdir/stbt-control.keymap
}

test_stbt_control_as_stbt_record_control_recorder__default_keymap() {
    cp "$testdir/stbt-control.keymap" "$XDG_CONFIG_HOME/stbt/control.conf" &&
    validate_stbt_record_control_recorder stbt-control;
    local ret=$?
    if [[ $ret -ne 0 ]] &&
        cat log | grep -q "Unable to print keymap because the terminal is too small";
    then
        skip "terminal is too narrow"
    fi
    return $ret
}

test_stbt_control_as_stbt_record_control_recorder__keymap_from_config() {
    set_config control.keymap "$testdir/stbt-control.keymap" &&
    validate_stbt_record_control_recorder stbt-control
}
