test_that_stbt_control_sends_a_single_key() {
    stbt-control --control none MENU &&
    cat "$scratchdir/log" | grep -q 'NullRemote: Ignoring request to press "MENU"'
}

test_stbt_control_unit_tests() {
    # Workaround for https://github.com/nose-devs/nose/issues/49
    cp ../stbt-control "$scratchdir/stbt-control.py"
    PYTHONPATH=.. nosetests --with-doctest -v "$scratchdir/stbt-control.py"
}

test_stbt_control_as_stbt_record_control_recorder() {
    cd "$scratchdir" &&
    cat > test.expect <<-EOF &&
	spawn stbt-record --control-recorder=stbt-control:$testdir/stbt-control.keymap
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
	stbt.wait_for_match('0000-gamut-complete.png')
	stbt.press('checkers-8')
	stbt.wait_for_match('0001-checkers-8-complete.png')
	stbt.press('smpte')
	stbt.wait_for_match('0002-smpte-complete.png')
	EOF
    diff -u expected test.py
}
