# coding: utf-8

import warnings
from collections import deque

from .config import ConfigurationError, get_config
from .diff import MotionDiff
from .imgutils import limit_time
from .logging import debug, draw_on
from .types import Region, UITestFailure


def detect_motion(timeout_secs=10, noise_threshold=None, mask=Region.ALL,
                  region=Region.ALL, frames=None):
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

    :param float noise_threshold:
        The amount of noise to ignore. This is only useful with noisy analogue
        video sources. Valid values range from 0 (all differences are
        considered noise; a value of 0 will never report motion) to 1.0 (any
        difference is considered motion).

        This defaults to 0.84. You can override the global default value by
        setting ``noise_threshold`` in the ``[motion]`` section of
        :ref:`.stbt.conf`.

    :param str|numpy.ndarray|Mask|Region mask:
        A `Region` or a mask that specifies which parts of the image to
        analyse. This accepts anything that can be converted to a Mask using
        `stbt.load_mask`. See :ref:`Masks`.

    :param Region region:
      Deprecated synonym for ``mask``. Use ``mask`` instead.

    :param Iterator[stbt.Frame] frames: An iterable of video-frames to analyse.
        Defaults to ``stbt.frames()``.

    Changed in v33: ``mask`` accepts anything that can be converted to a Mask
    using `load_mask`. The ``region`` parameter is deprecated; pass your
    `Region` to ``mask`` instead. You can't specify ``mask`` and ``region``
    at the same time.
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

    debug(f"Searching for motion, using mask={mask}")

    try:
        frame = next(frames)
    except StopIteration:
        return

    differ = detect_motion.differ(frame, mask, threshold=noise_threshold)
    for frame in frames:
        result = differ.diff(frame)
        draw_on(frame, result, label="detect_motion()")
        debug("%s found: %s" % (
            "Motion" if result.motion else "No motion", str(result)))
        yield result


detect_motion.differ = MotionDiff


def wait_for_motion(
        timeout_secs=10, consecutive_frames=None,
        noise_threshold=None, mask=Region.ALL, region=Region.ALL, frames=None):
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

    :param float noise_threshold: See `detect_motion`.
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
    def __init__(self, screenshot, mask, timeout_secs):
        super().__init__()
        self.screenshot = screenshot
        self.mask = mask
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find motion within %g seconds, using mask=%r" % (
            self.timeout_secs, self.mask)
