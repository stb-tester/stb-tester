# Tests that we can change the image given to templatematch.
# Also tests the remote-control infrastructure by using the null control.
wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
press("MENU")
wait_for_match("videotestsrc-bw.png", consecutive_matches=24)
press("OK")
wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
