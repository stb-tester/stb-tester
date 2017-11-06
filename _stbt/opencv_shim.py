"""Shim layer for OpenCV which works for both OpenCV v2 and v3.

This only contains translations for functionality which is needed by
`stb-tester`. When a translation is required, the naming and function signatures
from v3 are used.
"""

from __future__ import absolute_import

import warnings

import cv2

# The redefined builtins are `min`, `max`, `reduce`, `pow`
# pylint: disable=redefined-builtin
# pylint: disable=wildcard-import,unused-wildcard-import
from cv2 import *  # isort:skip


# Disable printing the source line of the warning, which is completely pointless
def _warning_no_traceback(message, category, filename, lineno, file=None, **_):
    warnings._show_warning(  # pylint: disable=protected-access
        message, category, filename, lineno, file=file, line='')


warnings.showwarning = _warning_no_traceback

# Upack the version number for opencv.  Some opencv versions have 4 parts
# (e.g. 2.4.12.2) and some have 3 (e.g. 3.2.0).
_cv2_split_version = [int(v) for v in cv2.__version__.split(".")]
CV_MAJOR_VERSION = _cv2_split_version[0]
CV_MINOR_VERSION = _cv2_split_version[1]
CV_SUBMINOR_VERSION = _cv2_split_version[2]

if CV_MAJOR_VERSION not in [2, 3]:
    raise RuntimeError("Unsupported OpenCV version %s" % cv2.__version__)

if CV_MAJOR_VERSION == 2:
    _cv_submod = getattr(cv2, 'cv')

    # functions

    def findContours(  # pylint: disable=function-redefined
        image, mode, method, contours=None, hierarchy=None, offset=None
    ):
        contours, hierarchy = cv2.findContours(
            image, mode, method, contours=contours, hierarchy=hierarchy,
            offset=offset)
        warnings.warn(
            "You are using OpenCV v2, so `opencv_shim.findContours` is "
            "returning `None` for `image`")
        return None, contours, hierarchy

    # `imread` flags
    IMREAD_GRAYSCALE = getattr(cv2, 'CV_LOAD_IMAGE_GRAYSCALE')
    IMREAD_COLOR = getattr(cv2, 'CV_LOAD_IMAGE_COLOR')
    IMREAD_UNCHANGED = getattr(cv2, 'CV_LOAD_IMAGE_UNCHANGED')

    # `imwrite` flags
    IMWRITE_JPEG_QUALITY = getattr(_cv_submod, 'CV_IMWRITE_JPEG_QUALITY')

    # polygon `thickness` arg
    FILLED = getattr(_cv_submod, 'CV_FILLED')
    # polygon/text `lineType` arg
    LINE_AA = getattr(cv2, 'CV_AA')

    # `findChessboardCorners` flags
    CALIB_CB_ADAPTIVE_THRESH = \
        getattr(_cv_submod, 'CV_CALIB_CB_ADAPTIVE_THRESH')