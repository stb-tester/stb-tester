# Run with ./run-tests.sh

start_fake_irnetbox() {
    waitfor() {
        for i in {1..100}; do grep "$1" "$2" && return; sleep 0.1; done;
        return 1
    }

    "$testdir"/fake-irnetbox > fake-irnetbox.log &
    fake_irnetbox=$!
    trap "kill $fake_irnetbox" EXIT
    waitfor "^PORT=" fake-irnetbox.log || fail "fake-irnetbox failed to start"
    irnetbox_port=$(awk -F= '/^PORT=/ { print $2 }' fake-irnetbox.log)
}

test_irnetbox_commands() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	import irnetbox
	rcu = irnetbox.RemoteControlConfig("$testdir/irnetbox.conf")
	with irnetbox.IRNetBox("localhost", $irnetbox_port) as ir:
	    ir.power_on()
	    ir.irsend_raw(port=1, power=100, data=rcu["MENU"])
	    ir.irsend_raw(port=1, power=100, data=rcu["OK"])
	EOF
    python test.py || return
    grep -q "Received message POWER_ON" fake-irnetbox.log ||
        fail "fake-irnetbox didn't receive POWER_ON message"
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}

test_stbt_run_irnetbox_control() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	press("MENU")
	press("OK")
	EOF
    stbt-run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || return
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}
