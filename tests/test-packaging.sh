# Run with ./run-tests.sh

test_importing_stbt_without_stbt_run() {
    cat > test.py <<-EOF
	import stbt, cv2
	assert stbt.match(
	    "$testdir/videotestsrc-redblue.png",
	    frame=cv2.imread("$testdir/videotestsrc-full-frame.png"))
	EOF
    python test.py
}
