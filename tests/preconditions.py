"""
'preconditions' module.

Load into stbt-run with: 'stbt-run --module=/path/to/preconditions.py'
"""

def checkers_via_gamut():
    """Change input video to "gamut" patterns, then "checkers" pattern"""
    wait_for_match("videotestsrc-redblue.png", consecutive_matches=24)
    press("15")
    wait_for_match("videotestsrc-gamut.png", consecutive_matches=24)
    press("10")
