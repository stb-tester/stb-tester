# coding: utf-8
"""Main stb-tester python package. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

from .config import ConfigurationError, get_config
from .core import *  # pylint:disable=W0401
from .logging import debug

__all__ = [
    "as_precondition",
    "ConfigurationError",
    "debug",
    "detect_match",
    "detect_motion",
    "draw_text",
    "frames",
    "get_config",
    "get_frame",
    "is_screen_black",
    "match",
    "match_text",
    "MatchParameters",
    "MatchResult",
    "MatchTimeout",
    "MotionResult",
    "MotionTimeout",
    "NoVideo",
    "ocr",
    "OcrMode",
    "Position",
    "PreconditionError",
    "press",
    "press_until_match",
    "Region",
    "save_frame",
    "TextMatchResult",
    "UITestError",
    "UITestFailure",
    "wait_for_match",
    "wait_for_motion",
]
