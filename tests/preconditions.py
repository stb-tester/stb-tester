from stbt import press, wait_for_match

def checkers_via_gamut():
    """Change input video to "gamut" patterns, then "checkers" pattern"""
    wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
    press("gamut")
    wait_for_match("videotestsrc-gamut.png", consecutive_matches=24)
    press("checkers-8")
