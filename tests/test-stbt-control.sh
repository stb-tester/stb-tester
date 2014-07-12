test_that_stbt_control_sends_a_single_key() {
    set_config global.verbose 1
    stbt control --control none MENU &&
    cat log | grep -q 'NullRemote: Ignoring request to press "MENU"'
}

validate_stbt_record_control_recorder() {
    control_uri=$1

    cat > test.expect <<-EOF &&
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
	
	
	stbt.press('gamut')
	stbt.wait_for_match('0001-gamut-complete.png')
	stbt.press('checkers-8')
	stbt.wait_for_match('0002-checkers-8-complete.png')
	stbt.press('smpte')
	stbt.wait_for_match('0003-smpte-complete.png')
	EOF
    diff -u expected test.py
}

test_stbt_control_as_stbt_record_control_recorder__explict_keymap() {
    validate_stbt_record_control_recorder \
        stbt-control:$testdir/stbt-control.keymap
}

test_stbt_control_as_stbt_record_control_recorder__default_keymap() {
    cp "$testdir/stbt-control.keymap" "$XDG_CONFIG_HOME/stbt/control.conf" &&
    validate_stbt_record_control_recorder stbt-control
}

test_stbt_control_as_stbt_record_control_recorder__keymap_from_config() {
    set_config control.keymap "$testdir/stbt-control.keymap" &&
    validate_stbt_record_control_recorder stbt-control
}
