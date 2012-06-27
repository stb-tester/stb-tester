# Run with ./run-tests.sh

test_wait_for_match() {
    stbt-run test-wait_for_match.py
}

test_wait_for_match_no_match() {
    rm -f screenshot.png
    ! stbt-run test-wait_for_match-no-match.py &&
    [ -f screenshot.png ]
}
