# Run with ./run-tests.sh

test_that_stbt_locks_video_capture_hardware() {
    which flock >/dev/null 2>&1 || {
        echo "'flock' isn't present on the system; skipping this test." >&2
        return 0;
    }

    cd "$scratchdir"
    sed "s,@LIBEXECDIR@/stbt,$srcdir," "$srcdir/stbt.in" > stbt

    cat > test.py <<-EOF
	import time
	time.sleep(2)
	wait_for_match("$testdir/videotestsrc-redblue.png")
	EOF

    /bin/sh stbt run test.py &
    stbt1_pid=$!
    sleep 1

    /bin/sh stbt run test.py
    stbt2_status=$?

    wait $stbt1_pid
    stbt1_status=$?
    echo stbt1_status: $stbt1_status
    echo stbt2_status: $stbt2_status

    [[ $stbt1_status -eq 0 && $stbt2_status -eq 2 ]]
}
