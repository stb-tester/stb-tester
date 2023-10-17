from __future__ import annotations

import warnings
from collections import deque
from typing import Iterator, Optional

from .config import ConfigurationError, get_config
from .diff import BGRDiff, Differ, MotionResult
from .imgutils import _image_region, limit_time, FrameT
from .logging import debug, draw_on
from .mask import MaskTypes
from .types import Region, UITestFailure


def detect_motion(
    timeout_secs: float = 10,
    noise_threshold: Optional[int] = None,
    mask: MaskTypes = Region.ALL,
    region: Region = Region.ALL,
    frames: Optional[Iterator[FrameT]] = None,
) -> Iterator[MotionResult]:
    """Generator that yields a sequence of one `MotionResult` for each frame
    processed from the device-under-test's video stream.

    The `MotionResult` indicates whether any motion was detected.

    Use it in a ``for`` loop like this::

        for motionresult in stbt.detect_motion():
            ...

    In most cases you should use `wait_for_motion` instead.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. After this timeout the iterator will be exhausted.
        Thas is, a ``for`` loop like ``for m in detect_motion(timeout_secs=10)``
        will terminate after 10 seconds. If ``timeout_secs`` is ``None`` then
        the iterator will yield frames forever. Note that you can stop
        iterating (for example with ``break``) at any time.

    :param int noise_threshold:
        The difference in pixel intensity to ignore. Valid values range from 0
        (any difference is considered motion) to 255 (which would never report
        motion).

        This defaults to 25. You can override the global default value by
        setting ``noise_threshold`` in the ``[motion]`` section of
        :ref:`.stbt.conf`.

    :param str|numpy.ndarray|Mask|Region mask:
        A `Region` or a mask that specifies which parts of the image to
        analyse. This accepts anything that can be converted to a Mask using
        `stbt.load_mask`. See :doc:`masks`.

    :param Region region:
      Deprecated synonym for ``mask``. Use ``mask`` instead.

    :param Iterator[stbt.Frame] frames: An iterable of video-frames to analyse.
        Defaults to ``stbt.frames()``.

    Changed in v33: ``mask`` accepts anything that can be converted to a Mask
    using `load_mask`. The ``region`` parameter is deprecated; pass your
    `Region` to ``mask`` instead. You can't specify ``mask`` and ``region``
    at the same time.

    Changed in v34: The difference-detection algorithm takes color into
    account. The ``noise_threshold`` parameter changed range (from 0.0-1.0 to
    0-255), sense (from "bigger is stricter" to "smaller is stricter"), and
    default value (from 0.84 to 25).
    """
    if frames is None:
        import stbt_core
        frames = stbt_core.frames()

    frames = limit_time(frames, timeout_secs)  # pylint: disable=redefined-variable-type

    if region is not Region.ALL:
        if mask is not Region.ALL:
            raise ValueError("Cannot specify mask and region at the same time")
        warnings.warn(
            "stbt.detect_motion: The 'region' parameter is deprecated; "
            "pass your Region to 'mask' instead",
            DeprecationWarning, stacklevel=2)
        mask = region

    if noise_threshold is None:
        noise_threshold = get_config('motion', 'noise_threshold', type_=int)

    debug(f"Searching for motion, using mask={mask}")

    try:
        frame = next(frames)
    except StopIteration:
        return

    differ = detect_motion.differ.replace(threshold=noise_threshold)
    dm = DetectMotion(differ, frame, mask)
    for frame in frames:
        result = dm.diff(frame)
        draw_on(frame, result, label="detect_motion()")
        debug("%s found: %s" % (
            "Motion" if result.motion else "No motion", str(result)))
        yield result


detect_motion.differ : Differ = BGRDiff()


class DetectMotion():
    """Concrete implementation of the `detect_motion` algorithm.

    This class is an internal implementation detail, not part of the public
    API. It isn't part of `detect_motion` because it offers a more convenient
    API for `press_and_wait` to use.

    Responsibilities of this class:

    - Remember the work done on already-seen frames (e.g. GrayscaleDiff's
      colorspace conversion).
    - The logic for when we update the "reference" frame.
    """
    def __init__(self, differ: Differ, initial_frame: FrameT,
                 mask: MaskTypes = Region.ALL):
        self.differ: Differ = differ
        self.mask_tuple = differ.preprocess_mask(
            mask, _image_region(initial_frame))
        self.prev_frame = differ.preprocess(initial_frame, self.mask_tuple)

    def diff(self, frame: FrameT) -> MotionResult:
        new_frame = self.differ.preprocess(frame, self.mask_tuple)
        motion = self.differ.diff(self.prev_frame, new_frame, self.mask_tuple)

        if motion:
            # Only update the comparison frame if it's different to the previous
            # one.  This makes `detect_motion` more sensitive to slow motion
            # because the differences between frames 1 and 2 might be small and
            # the differences between frames 2 and 3 might be small but we'd see
            # the difference by looking between 1 and 3.
            self.prev_frame = new_frame

        return motion


def wait_for_motion(
    timeout_secs: float = 10,
    consecutive_frames: "Optional[int | str]" = None,
    noise_threshold: Optional[int] = None,
    mask: MaskTypes = Region.ALL,
    region: Region = Region.ALL,
    frames: "Optional[Iterator[FrameT]]" = None,
) -> MotionResult:
    """Search for motion in the device-under-test's video stream.

    "Motion" is difference in pixel values between two frames.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. This function will raise `MotionTimeout` if no
        motion is detected within this time.

    :type consecutive_frames: int or str
    :param consecutive_frames:
        Considers the video stream to have motion if there were differences
        between the specified number of consecutive frames. This can be:

        * a positive integer value, or
        * a string in the form "x/y", where "x" is the number of frames with
          motion detected out of a sliding window of "y" frames.

        This defaults to "10/20". You can override the global default value by
        setting ``consecutive_frames`` in the ``[motion]`` section of
        :ref:`.stbt.conf`.

    :param int noise_threshold: See `detect_motion`.
    :param str|numpy.ndarray|Mask|Region mask: See `detect_motion`.
    :param Region region: See `detect_motion`.
    :param Iterator[stbt.Frame] frames: See `detect_motion`.

    :returns: `MotionResult` when motion is detected. The MotionResult's
        ``time`` and ``frame`` attributes correspond to the first frame in
        which motion was detected.
    :raises: `MotionTimeout` if no motion is detected after ``timeout_secs``
        seconds.

    Changed in v33: ``mask`` accepts anything that can be converted to a Mask
    using `load_mask`. The ``region`` parameter is deprecated; pass your
    `Region` to ``mask`` instead. You can't specify ``mask`` and ``region``
    at the same time.

    Changed in v34: The difference-detection algorithm takes color into
    account. The ``noise_threshold`` parameter changed range (from 0.0-1.0 to
    0-255), sense (from "bigger is stricter" to "smaller is stricter"), and
    default value (from 0.84 to 25).
    """
    if frames is None:
        import stbt_core
        frames = stbt_core.frames()

    if consecutive_frames is None:
        consecutive_frames = get_config('motion', 'consecutive_frames')

    consecutive_frames = str(consecutive_frames)
    if '/' in consecutive_frames:
        motion_frames = int(consecutive_frames.split('/')[0])
        considered_frames = int(consecutive_frames.split('/')[1])
    else:
        motion_frames = int(consecutive_frames)
        considered_frames = int(consecutive_frames)

    if motion_frames > considered_frames:
        raise ConfigurationError(
            "`motion_frames` exceeds `considered_frames`")

    if region is not Region.ALL:
        if mask is not Region.ALL:
            raise ValueError("Cannot specify mask and region at the same time")
        warnings.warn(
            "stbt.wait_for_motion: The 'region' parameter is deprecated; "
            "pass your Region to 'mask' instead",
            DeprecationWarning, stacklevel=2)
        mask = region

    debug("Waiting for %d out of %d frames with motion, using mask=%r" % (
        motion_frames, considered_frames, mask))

    matches = deque(maxlen=considered_frames)
    motion_count = 0
    last_frame = None
    for res in detect_motion(
            timeout_secs, noise_threshold, mask, frames=frames):
        motion_count += bool(res)
        if len(matches) == matches.maxlen:
            motion_count -= bool(matches.popleft())
        matches.append(res)
        if motion_count >= motion_frames:
            debug("Motion detected.")
            # We want to return the first True motion result as this is when
            # the motion actually started.
            for result in matches:
                if result:
                    return result
            assert False, ("Logic error in wait_for_motion: This code "
                           "should never be reached")
        last_frame = res.frame

    raise MotionTimeout(last_frame, mask, timeout_secs)


class MotionTimeout(UITestFailure):
    """Exception raised by `wait_for_motion`.

    :ivar Frame screenshot: The last video frame that `wait_for_motion` checked
        before timing out.

    :vartype mask: Mask or None
    :ivar mask: The mask that was used, if any.

    :vartype timeout_secs: int or float
    :ivar timeout_secs: Number of seconds that motion was searched for.
    """
    def __init__(self, screenshot: FrameT, mask: MaskTypes,
                 timeout_secs: float):
        super().__init__()
        self.screenshot: FrameT = screenshot
        self.mask: MaskTypes = mask
        self.timeout_secs: float = timeout_secs

    def __str__(self):
        return "Didn't find motion within %g seconds, using mask=%r" % (
            self.timeout_secs, self.mask)
