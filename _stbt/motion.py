# coding: utf-8

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

from collections import deque

import cv2

from .config import ConfigurationError, get_config
from .imgutils import (_frame_repr, _image_region, _ImageFromUser, _load_image,
                       pixel_bounding_box, crop, limit_time)
from .logging import debug, draw_on, ImageLogger
from .types import Region, UITestFailure


def detect_motion(timeout_secs=10, noise_threshold=None, mask=None,
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

    :type mask: str or `numpy.ndarray`
    :param mask:
        A black & white image that specifies which part of the image to search
        for motion. White pixels select the area to analyse; black pixels select
        the area to ignore. The mask must be the same size as the video frame.

        This can be a string (a filename that will be resolved as per
        `load_image`) or a single-channel image in OpenCV format.

    :type region: `Region`
    :param region:
        Only analyze the specified region of the video frame.

        If you specify both ``region`` and ``mask``, the mask must be the same
        size as the region.

    :type frames: Iterator[stbt.Frame]
    :param frames: An iterable of video-frames to analyse. Defaults to
        ``stbt.frames()``.

    | Added in v28: The ``region`` parameter.
    | Added in v29: The ``frames`` parameter.
    """
    if frames is None:
        import stbt
        frames = stbt.frames()

    frames = limit_time(frames, timeout_secs)  # pylint: disable=redefined-variable-type

    if noise_threshold is None:
        noise_threshold = get_config(
            'motion', 'noise_threshold', type_=float)

    debug("Searching for motion")

    if mask is None:
        mask = _ImageFromUser(None, None, None)
    else:
        mask = _load_image(mask, cv2.IMREAD_GRAYSCALE)
        debug("Using mask %s" % mask.friendly_name)

    try:
        frame = next(frames)
    except StopIteration:
        return

    region = Region.intersect(_image_region(frame), region)

    previous_frame_gray = cv2.cvtColor(crop(frame, region),
                                       cv2.COLOR_BGR2GRAY)
    if (mask.image is not None and
            mask.image.shape[:2] != previous_frame_gray.shape[:2]):
        raise ValueError(
            "The dimensions of the mask '%s' %s don't match the "
            "video frame %s" % (
                mask.friendly_name, mask.image.shape,
                previous_frame_gray.shape))

    for frame in frames:
        imglog = ImageLogger("detect_motion", region=region)
        imglog.imwrite("source", frame)
        imglog.set(roi=region, noise_threshold=noise_threshold)

        frame_gray = cv2.cvtColor(crop(frame, region), cv2.COLOR_BGR2GRAY)
        imglog.imwrite("gray", frame_gray)
        imglog.imwrite("previous_frame_gray", previous_frame_gray)

        absdiff = cv2.absdiff(frame_gray, previous_frame_gray)
        imglog.imwrite("absdiff", absdiff)

        if mask.image is not None:
            absdiff = cv2.bitwise_and(absdiff, mask.image)
            imglog.imwrite("mask", mask.image)
            imglog.imwrite("absdiff_masked", absdiff)

        _, thresholded = cv2.threshold(
            absdiff, int((1 - noise_threshold) * 255), 255,
            cv2.THRESH_BINARY)
        eroded = cv2.erode(
            thresholded,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        imglog.imwrite("absdiff_threshold", thresholded)
        imglog.imwrite("absdiff_threshold_erode", eroded)

        out_region = pixel_bounding_box(eroded)
        if out_region:
            # Undo cv2.erode above:
            out_region = out_region.extend(x=-1, y=-1)
            # Undo crop:
            out_region = out_region.translate(region)

        motion = bool(out_region)
        if motion:
            # Only update the comparison frame if it's different to the previous
            # one.  This makes `detect_motion` more sensitive to slow motion
            # because the differences between frames 1 and 2 might be small and
            # the differences between frames 2 and 3 might be small but we'd see
            # the difference by looking between 1 and 3.
            previous_frame_gray = frame_gray

        result = MotionResult(getattr(frame, "time", None), motion,
                              out_region, frame)
        draw_on(frame, result, label="detect_motion()")
        debug("%s found: %s" % (
            "Motion" if motion else "No motion", str(result)))
        _log_motion_image_debug(imglog, result)
        yield result


def wait_for_motion(
        timeout_secs=10, consecutive_frames=None,
        noise_threshold=None, mask=None, region=Region.ALL, frames=None):
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

    :param mask: See `detect_motion`.

    :param region: See `detect_motion`.

    :param frames: See `detect_motion`.

    :returns: `MotionResult` when motion is detected. The MotionResult's
        ``time`` and ``frame`` attributes correspond to the first frame in
        which motion was detected.
    :raises: `MotionTimeout` if no motion is detected after ``timeout_secs``
        seconds.

    | Added in v28: The ``region`` parameter.
    | Added in v29: The ``frames`` parameter.
    """
    if frames is None:
        import stbt
        frames = stbt.frames()

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

    debug("Waiting for %d out of %d frames with motion" % (
        motion_frames, considered_frames))

    if mask is None:
        mask = _ImageFromUser(None, None, None)
    else:
        mask = _load_image(mask, cv2.IMREAD_GRAYSCALE)
        debug("Using mask %s" % mask.friendly_name)

    matches = deque(maxlen=considered_frames)
    motion_count = 0
    last_frame = None
    for res in detect_motion(
            timeout_secs, noise_threshold, mask, region, frames):
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

    raise MotionTimeout(last_frame, mask.friendly_name, timeout_secs)


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

    Added in v28: The ``frame`` attribute.
    """
    _fields = ("time", "motion", "region", "frame")

    def __init__(self, time, motion, region, frame):
        self.time = time
        self.motion = motion
        self.region = region
        self.frame = frame

    def __bool__(self):
        return self.motion

    def __repr__(self):
        return (
            "MotionResult(time=%s, motion=%r, region=%r, frame=%s)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.motion, self.region, _frame_repr(self.frame)))


class MotionTimeout(UITestFailure):
    """Exception raised by `wait_for_motion`.

    :ivar Frame screenshot: The last video frame that `wait_for_motion` checked
        before timing out.

    :vartype mask: str or None
    :ivar mask: Filename of the mask that was used, if any.

    :vartype timeout_secs: int or float
    :ivar timeout_secs: Number of seconds that motion was searched for.
    """
    def __init__(self, screenshot, mask, timeout_secs):
        super(MotionTimeout, self).__init__()
        self.screenshot = screenshot
        self.mask = mask
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find motion%s within %g seconds." % (
            " (with mask '%s')" % self.mask if self.mask else "",
            self.timeout_secs)


def _log_motion_image_debug(imglog, result):
    if not imglog.enabled:
        return

    template = u"""\
        <h4>
          detect_motion:
          {{ "Found" if result.motion else "Didn't find" }} motion
        </h4>

        {{ annotated_image(result) }}

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

    imglog.html(template, result=result)
