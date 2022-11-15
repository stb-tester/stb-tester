from __future__ import annotations

from typing import Optional

import cv2
import numpy

from .imgutils import (
    Frame, FrameT, crop, _frame_repr, _image_region, pixel_bounding_box)
from .logging import ddebug, ImageLogger
from .mask import load_mask, MaskTypes
from .types import Region, SizeT


class MotionResult():
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

    def __init__(self, time: float, motion: bool, region: Region, frame: Frame):
        self.time: float = time
        self.motion: bool = motion
        self.region: Region = region
        self.frame: Frame = frame

    def __bool__(self) -> bool:
        return self.motion

    def __nonzero__(self) -> bool:
        return self.__bool__()

    def __repr__(self) -> str:
        return (
            "MotionResult(time=%s, motion=%r, region=%r, frame=%s)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.motion, self.region, _frame_repr(self.frame)))


class FrameDiffer():
    """Interface for different algorithms for diffing frames in a sequence.

    Say you have a sequence of frames A, B, C. Typically you will compare frame
    A against B, and then frame B against C. This is a class (not a function)
    so that you can remember work you've done on frame B, so that you don't
    repeat that work when you need to compare against frame C.
    """
    def diff(self, frame: FrameT):
        raise NotImplementedError(
            "%s.diff is not implemented" % self.__class__.__name__)


class BGRDiff(FrameDiffer):
    """Compares 2 frames by calculating the color distance between them.

    The algorithm is a simple euclidean distance between each pair of
    corresponding pixels in the 2 frames. The color difference is then
    binarized using the specified threshold: Values greater than the threshold
    are counted as differences (that is, motion). Then, an "erode" operation
    removes differences that are only 1 pixel wide or high. If any differences
    remain, the 2 frames are considered different.

    This is the default diffing algorithm for `find_selection_from_background`
    and `ocr`'s `text_color`.
    """

    def __init__(
        self,
        initial_frame: FrameT,
        mask: MaskTypes = Region.ALL,
        min_size: Optional[SizeT] = None,
        threshold: float = 25,
        erode: bool = True,
    ):
        self.prev_frame = initial_frame
        self.min_size = min_size
        self.threshold = threshold

        self.mask_, self.region = load_mask(mask).to_array(
            _image_region(initial_frame))

        if isinstance(erode, numpy.ndarray):  # For power users
            kernel = erode
        elif erode:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        else:
            kernel = None
        self.kernel = kernel

    def diff(self, frame: FrameT) -> MotionResult:
        imglog = ImageLogger("BGRDiff", region=self.region,
                             min_size=self.min_size, threshold=self.threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("previous_frame", self.prev_frame)

        mask_pixels = self.mask_
        cframe = crop(frame, self.region)
        cprev = crop(self.prev_frame, self.region)

        sqd = numpy.subtract(cframe, cprev, dtype=numpy.int32)
        sqd = (sqd[:, :, 0] ** 2 +
               sqd[:, :, 1] ** 2 +
               sqd[:, :, 2] ** 2)
        sqd = sqd.reshape(sqd.shape + (1,))

        if imglog.enabled:
            normalised = numpy.sqrt(sqd / 3)
            if mask_pixels is None:
                imglog.imwrite("sqd", normalised)
            else:
                imglog.imwrite("sqd",
                               normalised.astype(numpy.uint8) & mask_pixels)

        d = sqd >= (self.threshold ** 2) * 3
        if mask_pixels is not None:
            d = numpy.logical_and(d, mask_pixels)  # pylint:disable=assignment-from-no-return
            imglog.imwrite("mask", mask_pixels)
        d = d.astype(numpy.uint8)
        if imglog.enabled:
            imglog.imwrite("thresholded", d * 255)

        if self.kernel is not None:
            d = cv2.morphologyEx(d, cv2.MORPH_OPEN, self.kernel)
            if imglog.enabled:
                imglog.imwrite("eroded", d * 255)

        out_region = pixel_bounding_box(d)
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

        result = MotionResult(getattr(frame, "time", None), motion,
                              out_region, frame)
        ddebug(str(result))
        imglog.html(BGRDIFF_HTML, result=result)
        return result


BGRDIFF_HTML = """\
    <h4>
      BGRDiff:
      {{ "Found" if result.motion else "Didn't find" }} differences
    </h4>

    {{ annotated_image(result) }}

    <h5>Result:</h5>
    <pre><code>{{ result | escape }}</code></pre>

    {% if result.region and not result.motion %}
    <p>Found motion <code>{{ result.region | escape }}</code> smaller than
    min_size <code>{{ min_size | escape }}</code>.</p>
    {% endif %}

    <h5>Previous frame:</h5>
    <img src="previous_frame.png" />

    <h5>Differences:</h5>
    <img src="sqd.png" />

    {% if "mask" in images %}
    <h5>Mask:</h5>
    <img src="mask.png" />
    {% endif %}

    <h5>Differences above threshold ({{threshold}}):</h5>
    <img src="thresholded.png" />

    {% if "eroded" in images %}
    <h5>Eroded:</h5>
    <img src="eroded.png" />
    {% endif %}
"""


class GrayscaleDiff(FrameDiffer):
    """Compares 2 frames by converting them to grayscale, calculating
    pixel-wise absolute differences, and ignoring differences below a
    threshold.

    This is the default diffing algorithm for `wait_for_motion` and
    `press_and_wait`.
    """

    def __init__(
        self,
        initial_frame: FrameT,
        mask: MaskTypes = Region.ALL,
        min_size: Optional[SizeT] = None,
        threshold: float = 0.84,
        erode: bool = True,
    ):
        self.prev_frame = initial_frame
        self.min_size = min_size
        self.threshold = threshold

        self.mask_, self.region = load_mask(mask).to_array(
            _image_region(initial_frame))

        if isinstance(erode, numpy.ndarray):  # For power users
            kernel = erode
        elif erode:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        else:
            kernel = None
        self.kernel = kernel

        self.prev_frame_gray = self.gray(initial_frame)

    def gray(self, frame: FrameT):
        return cv2.cvtColor(crop(frame, self.region), cv2.COLOR_BGR2GRAY)

    def diff(self, frame: FrameT) -> MotionResult:
        frame_gray = self.gray(frame)

        imglog = ImageLogger("GrayscaleDiff", region=self.region,
                             min_size=self.min_size,
                             threshold=self.threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("gray", frame_gray)
        imglog.imwrite("previous_frame_gray", self.prev_frame_gray)

        absdiff = cv2.absdiff(self.prev_frame_gray, frame_gray)
        imglog.imwrite("absdiff", absdiff)

        if self.mask_ is not None:
            absdiff = cv2.bitwise_and(absdiff, self.mask_)
            imglog.imwrite("mask", self.mask_)
            imglog.imwrite("absdiff_masked", absdiff)

        _, thresholded = cv2.threshold(
            absdiff, int((1 - self.threshold) * 255), 255,
            cv2.THRESH_BINARY)
        imglog.imwrite("absdiff_threshold", thresholded)
        if self.kernel is not None:
            thresholded = cv2.morphologyEx(
                thresholded, cv2.MORPH_OPEN, self.kernel)
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
        imglog.html(GRAYSCALEDIFF_HTML, result=result)
        return result


GRAYSCALEDIFF_HTML = """\
    <h4>
      GrayscaleDiff:
      {{ "Found" if result.motion else "Didn't find" }} differences
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

    <h5>Binarized (threshold={{threshold}}):</h5>
    <img src="absdiff_threshold.png" />

    {% if "eroded" in images %}
    <h5>Eroded:</h5>
    <img src="absdiff_threshold_erode.png" />
    {% endif %}
"""
