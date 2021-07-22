# coding: utf-8

import cv2
import numpy

from .config import get_config
from .imgutils import (crop, _frame_repr, pixel_bounding_box, _validate_region)
from .logging import ddebug, ImageLogger
from .types import Region


class FrameDiffer(object):
    """Interface for different algorithms for diffing frames in a sequence.

    Say you have a sequence of frames A, B, C. Typically you will compare frame
    A against B, and then frame B against C. This is a class (not a function)
    so that you can remember work you've done on frame B, so that you don't
    repeat that work when you need to compare against frame C.
    """

    def __init__(self, initial_frame, region=Region.ALL, mask=None,
                 min_size=None):
        self.prev_frame = initial_frame
        self.region = _validate_region(self.prev_frame, region)
        self.mask = mask
        self.min_size = min_size
        if (self.mask is not None and
                self.mask.shape[:2] != (self.region.height, self.region.width)):
            raise ValueError(
                "The dimensions of the mask %s don't match the %s <%ix%i>"
                % (_frame_repr(self.mask),
                   "frame" if region == Region.ALL else "region",
                   self.region.width, self.region.height))

    def diff(self, frame):
        raise NotImplementedError(
            "%s.diff is not implemented" % self.__class__.__name__)


class MotionDiff(FrameDiffer):
    """The `wait_for_motion` diffing algorithm."""

    def __init__(self, initial_frame, region=Region.ALL, mask=None,
                 min_size=None, noise_threshold=None, erode=True):
        super(MotionDiff, self).__init__(initial_frame, region, mask, min_size)

        if noise_threshold is None:
            noise_threshold = get_config(
                'motion', 'noise_threshold', type_=float)
        self.noise_threshold = noise_threshold

        if isinstance(erode, numpy.ndarray):  # For power users
            kernel = erode
        elif erode:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        else:
            kernel = None
        self.kernel = kernel

        self.prev_frame_gray = self.gray(initial_frame)

    def gray(self, frame):
        return cv2.cvtColor(crop(frame, self.region), cv2.COLOR_BGR2GRAY)

    def diff(self, frame):
        frame_gray = self.gray(frame)

        imglog = ImageLogger("MotionDiff", region=self.region,
                             min_size=self.min_size,
                             noise_threshold=self.noise_threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("gray", frame_gray)
        imglog.imwrite("previous_frame_gray", self.prev_frame_gray)

        absdiff = cv2.absdiff(self.prev_frame_gray, frame_gray)
        imglog.imwrite("absdiff", absdiff)

        if self.mask is not None:
            absdiff = cv2.bitwise_and(absdiff, self.mask)
            imglog.imwrite("mask", self.mask)
            imglog.imwrite("absdiff_masked", absdiff)

        _, thresholded = cv2.threshold(
            absdiff, int((1 - self.noise_threshold) * 255), 255,
            cv2.THRESH_BINARY)
        imglog.imwrite("absdiff_threshold", thresholded)
        if self.kernel is not None:
            thresholded = cv2.morphologyEx(
                thresholded, cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
            imglog.imwrite("absdiff_threshold_erode", thresholded)

        out_region = pixel_bounding_box(thresholded)
        if out_region:
            # Undo crop:
            out_region = out_region.translate(self.region)

        motion = bool(out_region and (
            self.min_size is None or
            (out_region.width >= self.min_size[0] and
             out_region.height >= self.min_size[1])))

        if motion:
            # Only update the comparison frame if it's different to the previous
            # one.  This makes `detect_motion` more sensitive to slow motion
            # because the differences between frames 1 and 2 might be small and
            # the differences between frames 2 and 3 might be small but we'd see
            # the difference by looking between 1 and 3.
            self.prev_frame = frame
            self.prev_frame_gray = frame_gray

        result = MotionResult(getattr(frame, "time", None), motion,
                              out_region, frame)
        ddebug(str(result))
        imglog.html(MOTION_HTML, result=result)
        return result


class MotionResult(object):
    """The result from `detect_motion` and `wait_for_motion`.

    :ivar float time: The time at which the video-frame was captured, in
        seconds since 1970-01-01T00:00Z. This timestamp can be compared with
        system time (``time.time()``).

    :ivar bool motion: True if motion was found. This is the same as evaluating
        ``MotionResult`` as a bool. That is, ``if result:`` will behave the
        same as ``if result.motion:``.

    :ivar Region region: Bounding box where the motion was found, or ``None``
        if no motion was found.

    :ivar Frame frame: The video frame in which motion was (or wasn't) found.
    """
    _fields = ("time", "motion", "region", "frame")

    def __init__(self, time, motion, region, frame):
        self.time = time
        self.motion = motion
        self.region = region
        self.frame = frame

    def __bool__(self):
        return self.motion

    def __nonzero__(self):
        return self.__bool__()

    def __repr__(self):
        return (
            "MotionResult(time=%s, motion=%r, region=%r, frame=%s)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.motion, self.region, _frame_repr(self.frame)))


MOTION_HTML = u"""\
    <h4>
      detect_motion:
      {{ "Found" if result.motion else "Didn't find" }} motion
    </h4>

    {{ annotated_image(result) }}

    <h5>Result:</h5>
    <pre><code>{{ result | escape }}</code></pre>

    {% if result.region and not result.motion %}
    <p>Found motion <code>{{ result.region | escape }}</code> smaller than
    min_size <code>{{ min_size | escape }}</code>.</p>
    {% endif %}

    <h5>ROI Gray:</h5>
    <img src="gray.png" />

    <h5>Previous frame ROI Gray:</h5>
    <img src="previous_frame_gray.png" />

    <h5>Absolute difference:</h5>
    <img src="absdiff.png" />

    {% if "mask" in images %}
    <h5>Mask:</h5>
    <img src="mask.png" />
    <h5>Absolute difference – masked:</h5>
    <img src="absdiff_masked.png" />
    {% endif %}

    <h5>Threshold (noise_threshold={{noise_threshold}}):</h5>
    <img src="absdiff_threshold.png" />

    <h5>Eroded:</h5>
    <img src="absdiff_threshold_erode.png" />
"""
