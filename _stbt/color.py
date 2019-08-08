import cv2
import numpy as np


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
