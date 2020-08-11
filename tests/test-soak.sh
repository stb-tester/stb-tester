# Run with ./run-tests.sh

test_long_running_stbt_run_process_for_memory_leaks() {
    [[ -n "$STBT_RUN_SOAK_TESTS" ]] ||
        skip "Skipping because \$STBT_RUN_SOAK_TESTS isn't set"

    cat > test.py <<-EOF
	import os, time, stbt_core as stbt
	
	initial_rss = None
	
	def get_rss():
	    # See http://man7.org/linux/man-pages/man5/proc.5.html
	    with open("/proc/%s/stat" % os.getpid()) as f:
	        stat = f.read()
	    rss = int(stat.split()[23]) * 4
	    print("VmRSS: %s kB" % rss)
	    global initial_rss
	    if initial_rss is None:
	        initial_rss = rss
	    return rss
	
	print("Testing short stbt.frames")
	end_time = time.time() + 600  # 10 minutes
	while time.time() < end_time:
	    for frame in stbt.frames(timeout_secs=10):
	        stbt.match("$testdir/videotestsrc-redblue-flipped.png", frame)
	    assert get_rss() < initial_rss * 1.1
	
	print("Testing long stbt.frames")
	for frame in stbt.frames(timeout_secs=600):  # 10 minutes
	    stbt.match("$testdir/videotestsrc-redblue-flipped.png", frame)
	    if int(frame.time) % 10 == 0:
	        assert get_rss() < initial_rss * 1.1
	        time.sleep(1)
	
	print("Testing stbt.get_frame")
	end_time = time.time() + 600  # 10 minutes
	while time.time() < end_time:
	    frame = stbt.get_frame()
	    stbt.match("$testdir/videotestsrc-redblue-flipped.png", frame)
	    if int(frame.time) % 10 == 0:
	        assert get_rss() < initial_rss * 1.1
	        time.sleep(1)
	EOF
    stbt run -v \
        --source-pipeline="videotestsrc is-live=true ! \
            video/x-raw,format=BGR,width=1280,height=720,framerate=25/1" \
        test.py
}
