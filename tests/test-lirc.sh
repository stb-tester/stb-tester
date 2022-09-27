# Run with ./run-tests.sh

start_fake_lircd() {
    waitfor() {
        for i in {1..100}; do grep "$1" "$2" && return; sleep 0.1; done;
        return 1
    }

    $python "$testdir"/fake-lircd "$@" > fake-lircd.log &
    fake_lircd=$!
    trap "kill $fake_lircd" EXIT
    waitfor "^SOCKET=" fake-lircd.log || fail "fake-lircd failed to start"
    lircd_socket=$(awk -F= '/^SOCKET=/ { print $2 }' fake-lircd.log)
}

test_press_with_lirc() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.press("menu")
	stbt.press("ok")
	EOF
    stbt run -v --control lirc:$lircd_socket:test test.py || return
    grep -Eq "fake-lircd: Received: b?'?SEND_ONCE test menu" fake-lircd.log &&
    grep -Eq "fake-lircd: Received: b?'?SEND_ONCE test ok" fake-lircd.log ||
        fail "fake-lircd didn't receive 2 SEND_ONCE messages"
}

test_press_with_lirc_using_enum_for_key_name() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	from enum import Enum
	import stbt_core as stbt
	
	class Keys(Enum):
	    KEY_MENU = "KEY_MENU"
	    KEY_OK = "KEY_OK"
	
	stbt.press(Keys.KEY_MENU)
	stbt.press(Keys.KEY_OK)
	EOF
    stbt run -v --control lirc:$lircd_socket:test test.py || return
    cat fake-lircd.log
    grep -Eq "fake-lircd: Received: b?'?SEND_ONCE test KEY_MENU" fake-lircd.log &&
    grep -Eq "fake-lircd: Received: b?'?SEND_ONCE test KEY_OK" fake-lircd.log ||
        fail "fake-lircd didn't receive 2 SEND_ONCE messages"
}

test_that_press_fails_on_lircd_error() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.press("button_that_causes_error")
	EOF
    ! stbt run -v --control lirc:$lircd_socket:test test.py ||
        fail "Expected 'press' to raise exception"
    cat log | grep 'RuntimeError' | grep 'fake-lircd error' ||
        fail "Expected to see RuntimeError('fake-lircd error')"
}

test_that_press_times_out_when_lircd_doesnt_reply() {
    start_fake_lircd

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("button_that_causes_timeout")
	EOF
    $timeout 30s stbt run -v --control lirc:$lircd_socket:test test.py
    ret=$?
    [ $ret -eq $timedout ] && fail "'stbt run' timed out"
    [ $ret -ne 0 ] || fail "Expected 'press' to raise exception"
}

test_that_press_ignores_lircd_broadcast_messages_on_success() {
    start_fake_lircd

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("button_that_causes_sighup_and_broadcast_and_ack")
	EOF
    stbt run -v --control lirc:$lircd_socket:test test.py || return
}

test_that_press_ignores_lircd_broadcast_messages_on_error() {
    start_fake_lircd

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("button_that_causes_sighup_and_broadcast_and_error")
	EOF
    ! stbt run -v --control lirc:$lircd_socket:test test.py ||
        fail "Expected 'press' to raise exception"
    cat log | grep 'RuntimeError' | grep 'fake-lircd error' ||
        fail "Expected to see RuntimeError('fake-lircd error')"
}

test_that_press_ignores_lircd_broadcast_messages_on_no_reply() {
    start_fake_lircd

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("button_that_causes_sighup_and_broadcast_and_timeout")
	EOF
    $timeout 30s stbt run -v --control lirc:$lircd_socket:test test.py
    ret=$?
    [ $ret -eq $timedout ] && fail "'stbt run' timed out"
    [ $ret -ne 0 ] || fail "Expected 'press' to raise exception"
}

test_press_hold_secs_with_lirc() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	import stbt_core as stbt
	stbt.press("KEY_LEFT", hold_secs=0.1)
	with stbt.pressing("KEY_RIGHT"):
	    pass
	EOF

    stbt run -v --control lirc:$lircd_socket:test test.py ||
        fail "stbt run failed"

    grep -Eq "fake-lircd: Received: b?'?SEND_START test KEY_LEFT" fake-lircd.log &&
    grep -Eq "fake-lircd: Received: b?'?SEND_STOP test KEY_LEFT" fake-lircd.log ||
        fail "press: fake-lircd dind't see SEND_START and SEND_STOP"

    grep -Eq "fake-lircd: Received: b?'?SEND_START test KEY_RIGHT" fake-lircd.log &&
    grep -Eq "fake-lircd: Received: b?'?SEND_STOP test KEY_RIGHT" fake-lircd.log ||
        fail "pressing: fake-lircd didn't see SEND_START and SEND_STOP"
}
