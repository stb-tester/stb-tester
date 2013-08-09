# Run with ./run-tests.sh

test_extra_arguments() {
    cat > test.py <<-EOF
	import sys
	key, template = sys.argv[1:]
	press(key)
	wait_for_match(template, timeout_secs=1)
	EOF

    ! stbt-run -v test.py smpte "$testdir/videotestsrc-checkers-8.png" &&
    stbt-run -v test.py checkers-8 "$testdir/videotestsrc-checkers-8.png"
}
