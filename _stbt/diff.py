from __future__ import annotations

import typing

import cv2
import numpy

from .imgutils import Frame, FrameT, crop, _frame_repr, pixel_bounding_box
from .logging import debug, ddebug, ImageLogger
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


class UNSET:
    """Sentinel"""


class Differ:
    """An algorithm that compares two images or frames to find the differences
    between them.

    Subclasses of this class implement the actual diffing algorithms: See
    `BGRDiff` and `GrayscaleDiff`.
    """

    # This is a low level interface that allows us to customise how two images
    # or frames are compared. It's used by `detect_motion`/`wait_for_motion`
    # and `press_and_wait`.
    #
    # `Differ` is designed so we can efficiently implement `GrayscaleDiff`
    # without doing the colour -> grayscale conversion on the same image twice.
    # To avoid internal state the interface makes preprocessing explicit; the
    # caller (`DetectMotion`) is responsible for keeping track of that state.
    # This makes the classes hard to use, but that's ok — it's a low-level
    # interface intended mostly for internal use.
    #
    # The only public interface is the subclass constructors. The methods are
    # not intended for use by external code.

    _PreProcessedFrame: typing.TypeAlias
    _PreProcessedMask: typing.TypeAlias

    def replace(self, min_size=UNSET, threshold=UNSET, erode=UNSET):
        """
        Return a new Differ with the specified parameters replaced.

        Differs are immutable. This method allows creating a new differ,
        overriding some of the parameters.

        This is needed to allow passing parameters like `min_size` when calling
        functions like `press_and_wait`.

        :meta private:
        """
        raise NotImplementedError(
            "%s.replace is not implemented" % self.__class__.__name__)

    def preprocess_mask(
            self, mask: MaskTypes,
            frame_region: Region  # pylint:disable=unused-argument
    ) -> "_PreProcessedMask":
        """
        Pre-process a mask.  The returned value from this will be passed to
        `preprocess` and `diff`.

        :meta private:
        """
        return mask

    def preprocess(
            self, frame: FrameT,
            mask: "_PreProcessedMask"  # pylint:disable=unused-argument
    ) -> "_PreProcessedFrame":
        """
        Pre-process a frame.  The returned value from this will be passed to
        `diff`.  `mask_tuple` is the return value from `preprocess_mask`.

        :meta private:
        """
        return frame

    def diff(self, a: "_PreProcessedFrame", b: "_PreProcessedFrame",
             mask: "_PreProcessedMask") -> MotionResult:
        """
        Compare two frames.  `a` and `b` are the return values from
        `preprocess`.  `mask_tuple` is the return value from `preprocess_mask`.

        :meta private:
        """
        raise NotImplementedError(
            "%s.diff is not implemented" % self.__class__.__name__)


class BGRDiff(Differ):
    """Compares 2 frames by calculating the color distance between them.

    The algorithm calculates the euclidean distance in BGR colorspace between
    each pair of corresponding pixels in the 2 frames. This distance is then
    binarized using the specified threshold: Values smaller than the threshold
    are ignored. Then, an "erode" operation removes differences that are only 1
    pixel wide or high. If any differences remain, the 2 frames are considered
    different.

    This is the default diffing algorithm for `detect_motion`,
    `wait_for_motion`, `press_and_wait`, `find_selection_from_background`,
    and `ocr`'s `text_color`.
    """

    def __init__(
        self,
        min_size: SizeT | None = None,
        threshold: float = 25,
        erode: bool = True,
    ):
        self.min_size = min_size
        self.threshold = threshold

        if isinstance(erode, numpy.ndarray):  # For power users
            kernel = erode
        elif erode:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        else:
            kernel = None
        self.kernel = kernel

    def replace(self, min_size=UNSET, threshold=UNSET, erode=UNSET):
        if min_size is UNSET:
            min_size = self.min_size
        if threshold is UNSET:
            threshold = self.threshold
        if erode is UNSET:
            erode = self.kernel
        return self.__class__(min_size, threshold, erode)

    def preprocess_mask(
            self, mask: MaskTypes, frame_region: Region):
        return load_mask(mask).to_array(frame_region)

    def diff(self, a, b, mask):
        mask_pixels, region = mask
        prev_frame = a
        frame = b

        imglog = ImageLogger("BGRDiff", region=region,
                             min_size=self.min_size, threshold=self.threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("previous_frame", prev_frame)

        cframe = crop(frame, region)
        cprev = crop(prev_frame, region)

        d = _threshold_diff_bgr(cprev, cframe, (self.threshold ** 2) * 3,
                                imglog, mask_pixels)
        if mask_pixels is not None:
            numpy.bitwise_and(d, mask_pixels[:, :, 0], out=d)
            imglog.imwrite("mask", mask_pixels)

        if imglog.enabled:
            imglog.imwrite("thresholded", d * 255)

        if self.kernel is not None:
            d = cv2.morphologyEx(d, cv2.MORPH_OPEN, self.kernel)
            if imglog.enabled:
                imglog.imwrite("eroded", d * 255)

        out_region = pixel_bounding_box(d)
        if out_region:
            # Undo crop:
            out_region = out_region.translate(region)

        motion = bool(out_region and (
            self.min_size is None or
            (out_region.width >= self.min_size[0] and
             out_region.height >= self.min_size[1])))
        result = MotionResult(getattr(frame, "time", None), motion,
                              out_region, frame)
        ddebug(str(result))
        imglog.html(BGRDIFF_HTML, result=result)
        return result


def _threshold_diff_bgr(
        a: numpy.ndarray[numpy.uint8], b: numpy.ndarray[numpy.uint8],
        threshold: int,
        imglog: ImageLogger,
        mask_pixels: "numpy.ndarray[numpy.uint8] | None"
) -> numpy.ndarray[numpy.uint8]:

    if a.shape[:2] != b.shape[:2]:
        raise ValueError("Images must be the same size")
    if (len(a.shape) < 3 or a.shape[2] != 3 or
            len(b.shape) < 3 or b.shape[2] != 3):
        raise ValueError("Images must be 3-channel BGR images")
    try:
        from . import libstbt
        if not imglog.enabled:
            return libstbt.threshold_diff_bgr(a, b, threshold)
    except (ImportError, NotImplementedError) as e:
        debug("BGRDiff missed fast-path: %s" % e)

    return _threshold_diff_bgr_numpy(a, b, threshold, imglog, mask_pixels)


def _threshold_diff_bgr_numpy(
        a: numpy.ndarray[numpy.uint8], b: numpy.ndarray[numpy.uint8],
        threshold: int,
        imglog: "ImageLogger | None" = None,
        mask_pixels: "numpy.ndarray[numpy.uint8] | None" = None
) -> numpy.ndarray[numpy.uint8]:

    sqd = numpy.subtract(a, b, dtype=numpy.int32)
    sqd = (sqd[:, :, 0] ** 2 +
           sqd[:, :, 1] ** 2 +
           sqd[:, :, 2] ** 2)

    if imglog is not None and imglog.enabled:
        normalised = numpy.sqrt(sqd / 3)
        if mask_pixels is None:
            imglog.imwrite("sqd", normalised)
        else:
            imglog.imwrite("sqd",
                           normalised.astype(numpy.uint8) &
                           mask_pixels[:, :, 0])

    return (sqd >= threshold).astype(numpy.uint8)


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


class GrayscaleDiff(Differ):
    """Compares 2 frames by converting them to grayscale, calculating
    pixel-wise absolute differences, and ignoring differences below a
    threshold.

    This was the default diffing algorithm for `wait_for_motion` and
    `press_and_wait` before v34.
    """

    def __init__(
        self,
        min_size: SizeT | None = None,
        threshold: float = 0.84,
        erode: bool = True,
    ):
        self.min_size = min_size
        self.threshold = threshold

        if isinstance(erode, numpy.ndarray):  # For power users
            kernel = erode
        elif erode:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        else:
            kernel = None
        self.kernel = kernel

    def replace(self, min_size=UNSET, threshold=UNSET, erode=UNSET):
        if min_size is UNSET:
            min_size = self.min_size
        if threshold is UNSET:
            threshold = self.threshold
        if erode is UNSET:
            erode = self.kernel
        return self.__class__(min_size, threshold, erode)

    def preprocess_mask(
            self, mask: MaskTypes, frame_region: Region):
        return load_mask(mask).to_array(frame_region)

    def preprocess(self, frame, mask):
        _, region = mask
        return frame, cv2.cvtColor(crop(frame, region), cv2.COLOR_BGR2GRAY)

    def diff(self, a, b, mask) -> MotionResult:
        _, prev_frame_gray = a
        frame, frame_gray = b
        mask, region = mask

        imglog = ImageLogger("GrayscaleDiff", region=region,
                             min_size=self.min_size,
                             threshold=self.threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("gray", frame_gray)
        imglog.imwrite("previous_frame_gray", prev_frame_gray)

        absdiff = cv2.absdiff(prev_frame_gray, frame_gray)
        imglog.imwrite("absdiff", absdiff)

        if mask is not None:
            absdiff = cv2.bitwise_and(absdiff, mask)
            imglog.imwrite("mask", mask)
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
            out_region = out_region.translate(region)

        motion = bool(out_region and (
            self.min_size is None or
            (out_region.width >= self.min_size[0] and
             out_region.height >= self.min_size[1])))

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
