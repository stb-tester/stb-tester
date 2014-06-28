from stbt import press, wait_for_match


def checkers_via_gamut():
    """Change input video to "gamut" patterns, then "checkers" pattern"""
    wait_for_match("videotestsrc-redblue.png")
    press("gamut")
    wait_for_match("videotestsrc-gamut.png")
    press("checkers-8")
