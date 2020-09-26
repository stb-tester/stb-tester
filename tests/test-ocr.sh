# Run with ./run-tests.sh

test_ocr_on_live_video() {
    cat > test.py <<-EOF
	import stbt_core as stbt
	
	next(stbt.frames(timeout_secs=60))  # wait 'til video pipeline playing
	text = stbt.ocr()
	assert text == "Hello there", "Unexpected text: %s" % text
	
	text = stbt.ocr(region=stbt.Region(x=70, y=180, width=90, height=40))
	assert text == "Hello", "Unexpected text: %s" % text
	EOF
    stbt run -v \
        --source-pipeline="videotestsrc pattern=black ! \
                video/x-raw,format=BGR ! \
                textoverlay text=Hello\ there font-desc=Sans\ 48 ! \
                video/x-raw,format=BGR" \
        test.py
}

test_that_stbt_run_sets_up_caching() {
    stbt run -v $testdir/test_ocr.py::_test_that_cache_speeds_up_ocr
}
