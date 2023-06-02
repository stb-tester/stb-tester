# Run with ./run-tests.sh

test_record() {
    stbt record -v -o test.py --control-recorder=file://<(
        sleep 1; echo gamut;
        sleep 1; echo checkers-8;
        sleep 1; echo smpte; sleep 1;) &&
    diff -u - test.py <<-EOF &&
	import stbt_core as stbt
	
	
	def test_that_WRITE_TESTCASE_DESCRIPTION_HERE():
	    stbt.press('gamut')
	    stbt.wait_for_match('0001-gamut-complete.png')
	    stbt.press('checkers-8')
	    stbt.wait_for_match('0002-checkers-8-complete.png')
	    stbt.press('smpte')
	    stbt.wait_for_match('0003-smpte-complete.png')
	EOF
    [ -f 0001-gamut-complete.png ] &&
    [ -f 0002-checkers-8-complete.png ] &&
    [ -f 0003-smpte-complete.png ] &&
    cp "$testdir/videotestsrc-gamut.png" 0001-gamut-complete.png &&
    cp "$testdir/videotestsrc-checkers-8.png" 0002-checkers-8-complete.png &&
    cp "$testdir/videotestsrc-redblue.png" 0003-smpte-complete.png &&
    stbt run -v test.py
}

test_that_invalid_control_doesnt_hang_stbt_record() {
    timeout 10 stbt record --control asdf
    local ret=$?
    [ $ret -ne $timedout ] || fail "'stbt record --control asdf' timed out"
}
