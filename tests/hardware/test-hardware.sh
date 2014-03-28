# Run with ../run-tests.sh

hardware_test() {
    config="$1" &&
    echo "Testing with config: $config" &&
    "$testdir/hardware/$config.sh" start || fail "Setup of $config failed"

    stbt run -v --control=none "$testdir/hardware/test.py"
    exit_status=$?
    "$testdir/hardware/$config.sh" stop \
        || echo "WARNING: $config teardown failed"
    exit $exit_status
}

test_teradek_vidiu() {
    hardware_test teradek-vidiu
}

test_hauppauge_hdpvr() {
    hardware_test hauppauge-hdpvr
}

test_blackmagic_intensitypro() {
    hardware_test blackmagic-intensitypro
}
