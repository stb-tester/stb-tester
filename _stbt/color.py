from copy import deepcopy

import cv2
import numpy as np

import stbt


class Color(object):
    """
    The basic class to specify a color, defaults to be instantiated by HSV but can be parsed from BGR, all color values
    stored are `numpy.uint8`.
    """

    def __init__(self, hue, saturation, value):
        self.hue, self.saturation, self.value = np.array([hue, saturation, value], dtype=np.uint8)

    @property
    def hue(self):
        return self._hue

    @property
    def saturation(self):
        return self._saturation

    @property
    def value(self):
        return self._value

    @hue.setter
    def hue(self, value):
        if 0 <= value <= 179:
            self._hue = np.uint8(value)
        else:
            raise ValueError("Hue has to be 0-179")

    @saturation.setter
    def saturation(self, value):
        if 0 <= value <= 255:
            self._saturation = np.uint8(value)
        else:
            raise ValueError("Saturation has to be 0-255")

    @value.setter
    def value(self, value):
        if 0 <= value <= 255:
            self._value = np.uint8(value)
        else:
            raise ValueError("Value has to be 0-255")

    @property
    def np_array(self):
        return np.array([self.hue, self.saturation, self.value])

    def __repr__(self):
        return 'Color(hue=%r, saturation=%r, value=%r)' % (self.hue, self.saturation, self.value)

    @classmethod
    def from_bgr(cls, blue, green, red):
        [[[h, s, v]]] = cv2.cvtColor(np.uint8([[[blue, green, red]]]), cv2.COLOR_BGR2HSV)
        return cls(h, s, v)


def get_mask_by_color_range(hsv_starting_boundary, hsv_ending_boundary, frame=None, region=None):
    """
    The method to get a mask of a frame according to the range of color defined by two boundaries in HSV. The hue value
    goes cyclic from 0 to 179, if the target range of color overlaps the hue limits (e.g. a range of red between 0-10
    and 170-179), the method will mask each side of the hue limit separately and then combine them.

    :type hsv_starting_boundary: `Color`
    :param hsv_starting_boundary: The clockwise starting boundary of color in HSV

    :type hsv_ending_boundary: `Color`
    :param hsv_ending_boundary: The clockwise ending boundary of color in HSV

    :param frame: the target frame to mask, will grab a new frame from DUT if not defined.

    :type region: `Region`
    :param region: the ROI to mask, the rest of the frame will be ignored once defined.

    :return: `numpy.ndarray` the mask with value of 0 (black) or 255 (white) only.
    """
    frame = stbt.get_frame() if frame is None else frame
    # convert the color of the target frame from BGR to HSV for masking
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    if hsv_ending_boundary.hue < hsv_starting_boundary.hue:
        hsv_to_179 = deepcopy(hsv_ending_boundary)
        hsv_to_179.hue = 179
        hsv_from_0 = deepcopy(hsv_starting_boundary)
        hsv_from_0.hue = 0
        mask = cv2.bitwise_or(cv2.inRange(hsv_frame, hsv_starting_boundary.np_array, hsv_to_179.np_array),
                              cv2.inRange(hsv_frame, hsv_from_0.np_array, hsv_ending_boundary.np_array))
    else:
        mask = cv2.inRange(hsv_frame, hsv_starting_boundary.np_array, hsv_ending_boundary.np_array)

    # if the ROI is required then mask it again to only focus on the target region
    if region:
        roi = np.zeros_like(mask, dtype=np.uint8)
        cv2.rectangle(roi, (region.x, region.y), (region.right, region.bottom), color=255, thickness=cv2.FILLED)
        mask = cv2.bitwise_and(mask, mask, mask=roi)
    return mask
