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

test_script_accesses_its_path() {
    touch module.py
    cat > test.py <<-EOF
	import module
	print '__file__: ' + __file__
	EOF

    stbt-run -v test.py && cat log | grep '__file__: test.py'
}
