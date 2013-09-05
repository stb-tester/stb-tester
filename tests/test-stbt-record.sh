# Run with ./run-tests.sh

test_record_with_different_keys() {
    stbt-record -v -o test.py --control-recorder=file://<(
        sleep 1; echo gamut;
        sleep 1; echo checkers-8;
        sleep 1; echo smpte; sleep 1;) &&
    [ -f 0001-gamut-complete.png ] &&
    [ -f 0002-checkers-8-complete.png ] &&
    [ -f 0003-smpte-complete.png ] &&
    grep "wait_for_match" test.py &&
    ! grep "press_until_match" test.py &&
    cp "$testdir/videotestsrc-gamut.png" 0001-gamut-complete.png &&
    cp "$testdir/videotestsrc-checkers-8.png" 0002-checkers-8-complete.png &&
    cp "$testdir/videotestsrc-redblue.png" 0003-smpte-complete.png &&
    stbt-run -v test.py
}

test_record_with_multiple_presses_of_the_same_key() {
    stbt-record -v -o test.py --control-recorder=file://<(
        sleep 1; echo checkers-8;
        sleep 1; echo checkers-8;
        sleep 1; echo checkers-8; sleep 1;) &&
    [ -f 0001-checkers-8-complete.png ] &&
    [ ! -f 0002-checkers-8-complete.png ] &&
    [ ! -f 0003-checkers-8-complete.png ] &&
    grep "press_until_match" test.py &&
    ! grep "wait_for_match" test.py &&
    cp "$testdir/videotestsrc-checkers-8.png" 0001-checkers-8-complete.png &&
    stbt-run -v test.py
}

test_that_invalid_control_doesnt_hang_stbt_record() {
    timeout 10 stbt-record --control asdf
    local ret=$?
    [ $ret -ne $timedout ] || fail "'stbt-record --control asdf' timed out"
}
