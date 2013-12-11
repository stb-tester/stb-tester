# Run with ./run-tests.sh

start_fake_lircd() {
    waitfor() {
        for i in {1..100}; do grep "$1" "$2" && return; sleep 0.1; done;
        return 1
    }

    "$testdir"/fake-lircd "$@" > fake-lircd.log &
    fake_lircd=$!
    trap "kill $fake_lircd" EXIT
    waitfor "^SOCKET=" fake-lircd.log || fail "fake-lircd failed to start"
    lircd_socket=$(awk -F= '/^SOCKET=/ { print $2 }' fake-lircd.log)
}

test_press_with_lirc() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	press("menu")
	press("ok")
	EOF
    stbt-run -v --control lirc:$lircd_socket:test test.py || return
    grep -q "fake-lircd: Received: SEND_ONCE test menu" fake-lircd.log &&
    grep -q "fake-lircd: Received: SEND_ONCE test ok" fake-lircd.log ||
        fail "fake-lircd didn't receive 2 SEND_ONCE messages"
}

test_that_press_fails_on_lircd_error() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	press("button_that_causes_error")
	EOF
    ! stbt-run -v --control lirc:$lircd_socket:test test.py ||
        fail "Expected 'press' to raise exception"
    cat log | grep 'UITestError' | grep 'fake-lircd error' ||
        fail "Expected to see UITestError('fake-lircd error')"
}

test_that_press_times_out_when_lircd_doesnt_reply() {
    start_fake_lircd

    cat > test.py <<-EOF
	press("button_that_causes_timeout")
	EOF
    timeout 10s stbt-run -v --control lirc:$lircd_socket:test test.py
    ret=$?
    [ $? -eq $timedout ] && fail "'press' timed out"
    [ $? -ne 0 ] || fail "Expected 'press' to raise exception"
}

test_that_press_ignores_lircd_broadcast_messages_on_success() {
    start_fake_lircd

    cat > test.py <<-EOF
	press("button_that_causes_sighup_and_broadcast_and_ack")
	EOF
    stbt-run -v --control lirc:$lircd_socket:test test.py || return
}

test_that_press_ignores_lircd_broadcast_messages_on_error() {
    start_fake_lircd

    cat > test.py <<-EOF
	press("button_that_causes_sighup_and_broadcast_and_error")
	EOF
    ! stbt-run -v --control lirc:$lircd_socket:test test.py ||
        fail "Expected 'press' to raise exception"
    cat log | grep 'UITestError' | grep 'fake-lircd error' ||
        fail "Expected to see UITestError('fake-lircd error')"
}

test_that_press_ignores_lircd_broadcast_messages_on_no_reply() {
    start_fake_lircd

    cat > test.py <<-EOF
	press("button_that_causes_sighup_and_broadcast_and_timeout")
	EOF
    timeout 10s stbt-run -v --control lirc:$lircd_socket:test test.py
    ret=$?
    [ $? -eq $timedout ] && fail "'press' timed out"
    [ $? -ne 0 ] || fail "Expected 'press' to raise exception"
}

test_hold_with_lirc() {
    start_fake_lircd

    cat > test.py <<-EOF &&
	import stbt
	with stbt.hold("left"):
	    pass
	EOF
    stbt-run -v --control lirc:$lircd_socket:test test.py || return
    grep -q "fake-lircd: Received: SEND_START test left" fake-lircd.log &&
    grep -q "fake-lircd: Received: SEND_STOP test left" fake-lircd.log ||
        fail "fake-lircd didn't receive SEND_START and SEND_STOP messages"
}
