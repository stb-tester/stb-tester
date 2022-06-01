# coding: utf-8

"""
Copyright 2014 YouView TV Ltd.
Copyright 2014-2018 stb-tester.com Ltd.

License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import cv2

from .config import get_config
from .imgutils import (crop, _frame_repr, load_mask, pixel_bounding_box,
                       _validate_region)
from .logging import debug, ImageLogger
from .types import Region


def is_screen_black(frame=None, mask=None, threshold=None, region=Region.ALL):
    """Check for the presence of a black screen in a video frame.

    :type frame: `stbt.Frame` or `numpy.ndarray`
    :param frame:
      If this is specified it is used as the video frame to check; otherwise a
      new frame is grabbed from the device-under-test. This is an image in
      OpenCV format (for example as returned by `frames` and `get_frame`).

    :type mask: str or `numpy.ndarray`
    :param mask:
        A black & white image that specifies which part of the image to
        analyse. White pixels select the area to analyse; black pixels select
        the area to ignore.

        This can be a string (a filename that will be resolved as per
        `stbt.load_image`) or a single-channel image in OpenCV format.

        If you specify ``region``, the mask must be the same size as the
        region. Otherwise the mask must be the same size as the frame.

    :param int threshold:
      Even when a video frame appears to be black, the intensity of its pixels
      is not always 0. To differentiate almost-black from non-black pixels, a
      binary threshold is applied to the frame. The ``threshold`` value is in
      the range 0 (black) to 255 (white). The global default (20) can be
      changed by setting ``threshold`` in the ``[is_screen_black]`` section of
      :ref:`.stbt.conf`.

    :type region: `Region`
    :param region:
        Only analyze the specified region of the video frame.

    :returns:
        An object that will evaluate to true if the frame was black, or false
        if not black. The object has the following attributes:

        * **black** (*bool*) – True if the frame was black.
        * **frame** (`stbt.Frame`) – The video frame that was analysed.
    """
    if threshold is None:
        threshold = get_config('is_screen_black', 'threshold', type_=int)

    if frame is None:
        from stbt_core import get_frame
        frame = get_frame()

    region = _validate_region(frame, region)
    if mask is not None:
        mask = load_mask(mask)

    imglog = ImageLogger("is_screen_black", region=region, threshold=threshold)
    imglog.imwrite("source", frame)

    greyframe = cv2.cvtColor(crop(frame, region), cv2.COLOR_BGR2GRAY)
    if mask is not None:
        mask_ = mask.to_array(shape=(region.height, region.width, 1))
        imglog.imwrite("mask", mask_)
        cv2.bitwise_and(greyframe, mask_, dst=greyframe)
    maxVal = greyframe.max()

    result = _IsScreenBlackResult(bool(maxVal <= threshold), frame)
    debug("is_screen_black: {found} black screen using mask={mask}, "
          "threshold={threshold}, region={region}: "
          "{result}, maximum_intensity={maxVal}".format(
              found="Found" if result.black else "Didn't find",
              mask=mask,
              threshold=threshold,
              region=region,
              result=result,
              maxVal=maxVal))

    if imglog.enabled:
        imglog.imwrite("grey", greyframe)
        _, thresholded = cv2.threshold(greyframe, threshold, 255,
                                       cv2.THRESH_BINARY)
        imglog.imwrite("non_black", thresholded)
        imglog.set(maxVal=maxVal,
                   non_black_region=pixel_bounding_box(thresholded))
    _log_image_debug(imglog, result)

    return result


class _IsScreenBlackResult():
    def __init__(self, black, frame):
        self.black = black
        self.frame = frame

    def __bool__(self):
        return self.black

    def __repr__(self):
        return ("_IsScreenBlackResult(black=%r, frame=%s)" % (
            self.black,
            _frame_repr(self.frame)))


def _log_image_debug(imglog, result):
    if not imglog.enabled:
        return

    template = """\
        <h4>is_screen_black: {{result.black}}</h4>

        {{ annotated_image(non_black_region) }}

        {% if "mask" in images %}
        <h5>Mask:</h5>
        <img src="mask.png" />
        {% endif %}

        <h5>Greyscale, masked:</h5>
        <img src="grey.png">
        <ul>
          <li>Maximum pixel intensity: {{maxVal}}
          <li>threshold={{threshold}}
        </ul>

        {% if not result.black %}
        <h5>Non-black pixels in region:</h5>
        <img src="non_black.png" />
        {% endif %}
    """

    imglog.html(template, result=result)
