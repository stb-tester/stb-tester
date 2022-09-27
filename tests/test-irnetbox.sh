# Run with ./run-tests.sh

start_fake_irnetbox() {
    waitfor() {
        for i in {1..100}; do grep "$1" "$2" && return; sleep 0.1; done;
        return 1
    }

    PYTHONPATH=$srcdir $python "$testdir"/fake-irnetbox "$@" \
        > fake-irnetbox.log &
    fake_irnetbox=$!
    trap "kill $fake_irnetbox" EXIT
    waitfor "^PORT=" fake-irnetbox.log || fail "fake-irnetbox failed to start"
    irnetbox_port=$(awk -F= '/^PORT=/ { print $2 }' fake-irnetbox.log)
}

test_irnetbox_commands() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	from _stbt import irnetbox
	rcu = irnetbox.RemoteControlConfig("$testdir/irnetbox.conf")
	with irnetbox.IRNetBox("localhost", $irnetbox_port) as ir:
	    ir.power_on()
	    ir.irsend_raw(port=1, power=100, data=rcu["MENU"])
	    ir.irsend_raw(port=1, power=100, data=rcu["OK"])
	EOF
    PYTHONPATH=$srcdir $python test.py || return
    grep -q "Received message POWER_ON" fake-irnetbox.log ||
        fail "fake-irnetbox didn't receive POWER_ON message"
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}

test_stbt_run_irnetbox_control() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("MENU")
	stbt.press("OK")
	EOF
    stbt run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || return
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}

test_that_press_fails_on_irnetbox_error() {
    start_fake_irnetbox error

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("MENU")
	EOF
    ! stbt run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || fail "Expected 'press' to raise exception"
    cat log | grep -q "IRNetBox returned ERROR" ||
        fail "Didn't receive IRNetBox ERROR"
}

test_that_press_fails_on_irnetbox_nack() {
    start_fake_irnetbox nack

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("MENU")
	EOF
    ! stbt run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || fail "Expected 'press' to raise exception"
    cat log | grep -q "IRNetBox returned NACK" ||
        fail "Didn't receive IRNetBox NACK"
}

test_that_press_waits_for_irnetbox_async_complete() {
    start_fake_irnetbox wait

    cat > test.py <<-EOF
	import time, stbt_core as stbt
	before = time.time()
	print("Before press: %d" % before)
	stbt.press("MENU")
	after = time.time()
	print("After press: %d" % after)
	assert after - before > 1, "'press' returned too quickly"
	EOF
    stbt run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py
}

test_that_press_times_out_when_irnetbox_doesnt_reply() {
    start_fake_irnetbox noreply

    cat > test.py <<-EOF
	import stbt_core as stbt
	stbt.press("MENU")
	EOF
    ! stbt run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || fail "Expected 'press' to raise exception"
    cat log | grep -Eq 'socket.timeout|TimeoutError' ||
        fail "Didn't raise TimeoutError"
}
