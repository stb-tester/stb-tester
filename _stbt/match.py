"""
Copyright 2012-2014 YouView TV Ltd and contributors.
Copyright 2013-2022 stb-tester.com Ltd.

License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import annotations

import enum
import itertools
from collections import namedtuple
from typing import Iterator, Optional

import cv2
import numpy

from . import cv2_compat
from .config import ConfigurationError, get_config
from .imgproc_cache import memoize_iterator
from .imgutils import (
    Frame, crop, FrameT, _frame_repr, ImageT, _image_region, limit_time,
    load_image, _validate_region)
from .logging import (_Annotation, ddebug, debug, draw_on, draw_source_region,
                      get_debug_level, ImageLogger)
from .sqdiff import sqdiff
from .types import Position, Region, UITestFailure
from .utils import to_unicode


class MatchMethod(enum.Enum):
    """An enum. See `MatchParameters` for documentation of these values."""

    SQDIFF = "sqdiff"
    SQDIFF_NORMED = "sqdiff-normed"
    CCORR_NORMED = "ccorr-normed"
    CCOEFF_NORMED = "ccoeff-normed"

    # For nicer formatting in generated API documentation:
    def __repr__(self):
        return str(self)


class ConfirmMethod(enum.Enum):
    """An enum. See `MatchParameters` for documentation of these values."""

    NONE = "none"
    ABSDIFF = "absdiff"
    NORMED_ABSDIFF = "normed-absdiff"

    # For nicer formatting in generated API documentation:
    def __repr__(self):
        return str(self)


class MatchParameters():
    """Parameters to customise the image processing algorithm used by
    `match`, `wait_for_match`, and `press_until_match`.

    You can change the default values for these parameters by setting a key
    (with the same name as the corresponding python parameter) in the
    ``[match]`` section of :ref:`.stbt.conf`. But we strongly recommend that
    you don't change the default values from what is documented here.

    You should only need to change these parameters when you're trying to match
    a reference image that isn't actually a perfect match -- for example if
    there's a translucent background with live TV visible behind it; or if you
    have a reference image of a button's background and you want it to match
    even if the text on the button doesn't match.

    :type match_method: `MatchMethod`
    :param match_method:
      The method to be used by the first pass of stb-tester's image matching
      algorithm, to find the most likely location of the reference image within
      the larger source image. For details see OpenCV's
      :ocv:pyfunc:`cv2.matchTemplate`. Defaults to ``MatchMethod.SQDIFF``.

    :param float match_threshold:
      Overall similarity threshold for the image to be considered a match. This
      threshold applies to the *average* similarity across all pixels in the
      image. Valid values range from 0 (anything is considered to match) to 1
      (the match has to be pixel perfect). Defaults to 0.98.

    :type confirm_method: `ConfirmMethod`
    :param confirm_method:
      The method to be used by the second pass of stb-tester's image matching
      algorithm, to confirm that the region identified by the first pass is a
      good match.

      The first pass often gives false positives: It can report a "match" for
      an image with obvious differences, if the differences are local to a
      small part of the image. The second pass is more CPU-intensive, but it
      only checks the position of the image that the first pass identified. The
      allowed values are:

      :ConfirmMethod.NONE:
        Do not confirm the match. This is useful if you know that the reference
        image is different in some of the pixels. For example to find a button,
        even if the text inside the button is different.

      :ConfirmMethod.ABSDIFF:
        Compare the absolute difference of each pixel from the reference image
        against its counterpart from the candidate region in the source video
        frame.

      :ConfirmMethod.NORMED_ABSDIFF:
        Normalise the pixel values from both the reference image and the
        candidate region in the source video frame, then compare the absolute
        difference as with ``ABSDIFF``.

        This method is better at noticing differences in low-contrast images
        (compared to the ``ABSDIFF`` method), but it isn't suitable for
        reference images that don't have any structure (that is, images that
        are a single solid color without any lines or variation).

        This is the default method, with a default ``confirm_threshold`` of
        0.70.

    :param float confirm_threshold:
      The minimum allowed similarity between any given pixel in the reference
      image and the corresponding pixel in the source video frame, as a
      fraction of the pixel's total luminance range.

      Unlike ``match_threshold``, this threshold applies to each pixel
      individually: Any pixel that exceeds this threshold will cause the match
      to fail (but see ``erode_passes`` below).

      Valid values range from 0 (less strict) to 1.0 (more strict). Useful
      values tend to be around 0.84 for ``ABSDIFF``, and 0.70 for
      ``NORMED_ABSDIFF``. Defaults to 0.70.

    :param int erode_passes:
      After the ``ABSDIFF`` or ``NORMED_ABSDIFF`` absolute difference is taken,
      stb-tester runs an erosion algorithm that removes single-pixel differences
      to account for noise and slight rendering differences. Useful values are
      1 (the default) and 0 (to disable this step).

    """

    def __init__(
        self,
        match_method: Optional[MatchMethod] = None,
        match_threshold: Optional[float] = None,
        confirm_method: Optional[ConfirmMethod] = None,
        confirm_threshold: Optional[float] = None,
        erode_passes: Optional[int] = None,
    ):

        if match_method is None:
            match_method = get_config(
                'match', 'match_method', type_=MatchMethod)
        if match_threshold is None:
            match_threshold = get_config(
                'match', 'match_threshold', type_=float)
        if confirm_method is None:
            confirm_method = get_config(
                'match', 'confirm_method', type_=ConfirmMethod)
        if confirm_threshold is None:
            confirm_threshold = get_config(
                'match', 'confirm_threshold', type_=float)
        if erode_passes is None:
            erode_passes = get_config('match', 'erode_passes', type_=int)

        match_method = MatchMethod(match_method)
        confirm_method = ConfirmMethod(confirm_method)

        self.match_method: MatchMethod = match_method
        self.match_threshold: float = match_threshold
        self.confirm_method: ConfirmMethod = confirm_method
        self.confirm_threshold: float = confirm_threshold
        self.erode_passes: int = erode_passes

    def __repr__(self) -> str:
        return (
            "MatchParameters(match_method=%r, match_threshold=%r, "
            "confirm_method=%r, confirm_threshold=%r, erode_passes=%r)"
            % (self.match_method, self.match_threshold,
               self.confirm_method, self.confirm_threshold, self.erode_passes))


class MatchResult():
    """The result from `match`.

    :ivar float time: The time at which the video-frame was captured, in
        seconds since 1970-01-01T00:00Z. This timestamp can be compared with
        system time (``time.time()``).

    :ivar bool match: True if a match was found. This is the same as evaluating
        ``MatchResult`` as a bool. That is, ``if result:`` will behave the same
        as ``if result.match:``.

    :ivar Region region: Coordinates where the image was found (or of the
        nearest match, if no match was found).

    :ivar float first_pass_result: Value between 0 (poor) and 1.0 (excellent
        match) from the first pass of stb-tester's image matching algorithm
        (see `MatchParameters` for details).

    :ivar Frame frame: The video frame that was searched, as given to `match`.

    :ivar Image image: The reference image that was searched for, as given to
        `match`.
    """
    _fields = ("time", "match", "region", "first_pass_result", "frame", "image")

    def __init__(
            self, time, match, region,  # pylint: disable=redefined-outer-name
            first_pass_result, frame, image, _first_pass_matched=None):
        self.time: Optional[float] = time
        self.match: bool = match
        self.region: Region = region
        self.first_pass_result: float = first_pass_result
        self.frame: FrameT = frame
        self.image: ImageT = image
        self._first_pass_matched = _first_pass_matched

    def __repr__(self):
        return (
            "MatchResult(time=%s, match=%r, region=%r, first_pass_result=%r, "
            "frame=%s, image=%s)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.match,
                self.region,
                self.first_pass_result,
                _frame_repr(self.frame),
                _frame_repr(self.image)))

    def __bool__(self):
        return self.match

    @property
    def position(self) -> Position:
        return Position(self.region.x, self.region.y)


def match(
    image: ImageT,
    frame: Optional[FrameT] = None,
    match_parameters: Optional[MatchParameters] = None,
    region: Region = Region.ALL,
) -> MatchResult:
    """
    Search for an image in a single video frame.

    :type image: string or `numpy.ndarray`
    :param image:
      The image to search for. It can be the filename of a png file on disk, or
      a numpy array containing the pixel data in 8-bit BGR format. If the image
      has an alpha channel, any transparent pixels are ignored.

      Filenames should be relative paths. See `stbt.load_image` for the path
      lookup algorithm.

      8-bit BGR numpy arrays are the same format that OpenCV uses for images.
      This allows generating reference images on the fly (possibly using
      OpenCV) or searching for images captured from the device-under-test
      earlier in the test script.

    :type frame: `stbt.Frame` or `numpy.ndarray`
    :param frame:
      If this is specified it is used as the video frame to search in;
      otherwise a new frame is grabbed from the device-under-test. This is an
      image in OpenCV format (for example as returned by `frames` and
      `get_frame`).

    :type match_parameters: `MatchParameters`
    :param match_parameters:
      Customise the image matching algorithm. See `MatchParameters` for details.

    :type region: `Region`
    :param region:
      Only search within the specified region of the video frame.

    :returns:
      A `MatchResult`, which will evaluate to true if a match was found,
      false otherwise.
    """
    result = next(_match_all(image, frame, match_parameters, region))
    if result.match:
        debug("Match found: %s" % str(result))
    else:
        debug("No match found. Closest match: %s" % str(result))
    return result


def match_all(
    image: ImageT,
    frame: Optional[FrameT] = None,
    match_parameters: Optional[MatchParameters] = None,
    region: Region = Region.ALL,
) -> Iterator[MatchResult]:
    """
    Search for all instances of an image in a single video frame.

    Arguments are the same as `match`.

    :returns:
      An iterator of zero or more `MatchResult` objects (one for each position
      in the frame where ``image`` matches).

    Examples:

    .. code-block:: python

        all_buttons = list(stbt.match_all("button.png"))

    .. code-block:: python

        for match_result in stbt.match_all("button.png"):
            # do something with match_result here
            ...
    """
    any_matches = False
    for result in _match_all(image, frame, match_parameters, region):
        if result.match:
            debug("Match found: %s" % str(result))
            any_matches = True
            yield result
        else:
            if not any_matches:
                debug("No match found. Closest match: %s" % str(result))
            break


def _norm_frame(frame: FrameT) -> FrameT:
    """Normalise single channel images to shape (h, w, 3) rather than (h, w) or
    (h, w, 1).  match has the invariant that it behaves the same as if you'd
    run `frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)` first.

    We fiddle with the strides of the numpy array to avoid copying the data.
    """
    if not isinstance(frame, numpy.ndarray):
        raise TypeError(
            "Expected numpy.ndarray, got %r" % (type(frame).__name__,))
    if frame.dtype != numpy.uint8:
        raise TypeError(
            "Expected numpy.ndarray of uint8, got %r" % (frame.dtype,))
    frame = frame.view()
    if frame.ndim == 2:
        frame.shape = frame.shape + (1,)
    if frame.ndim != 3:
        raise ValueError(
            "Invalid shape for frame: %r. Shape must have 2 or 3 elements" %
            (frame.shape,))
    if frame.shape[2] not in (1, 3):
        raise ValueError(
            "Invalid shape for frame: %r. Shape must have 1 or 3 channels" %
            (frame.shape,))
    if frame.shape[2] == 1:
        frame = numpy.lib.stride_tricks.as_strided(  # type:ignore
            frame, frame.shape[:2] + (3,), frame.strides[:2] + (0,),
            subok=True, writeable=False)
    return frame


def test_norm_frame():
    frame = Frame(
        numpy.random.randint(256, size=(5, 5, 1), dtype=numpy.uint8), time=56)
    normed = _norm_frame(frame)
    assert normed.shape == (5, 5, 3)
    assert isinstance(normed, Frame)
    assert normed.time == 56
    assert numpy.all(normed[:, :, 0] == normed[:, :, 1])
    assert numpy.all(normed[:, :, 0] == normed[:, :, 2])


def _match_all(image, frame: Optional[FrameT], match_parameters, region):
    """
    Generator that yields a sequence of zero or more truthy MatchResults,
    followed by a falsey MatchResult.
    """
    if match_parameters is None:
        match_parameters = MatchParameters()

    if frame is None:
        from stbt_core import get_frame
        frame = get_frame()

    # Normalise single channel images to shape (h, w, 3) rather than just (h, w)
    frame = _norm_frame(frame)

    t = load_image(image, color_channels=(3, 4))

    if any(frame.shape[x] < t.shape[x] for x in (0, 1)):
        raise ValueError("Frame %r must be larger than reference image %r"
                         % (frame.shape, t.shape))
    if any(t.shape[x] < 1 for x in (0, 1)):
        raise ValueError("Reference image %r must contain some data"
                         % (t.shape,))

    if t.shape[2] == 4:
        if cv2_compat.version < [3, 0, 0]:
            raise ValueError(
                "Reference image %s has alpha channel, but transparency "
                "support requires OpenCV 3.0 or greater (you have %s)."
                % (t.relative_filename, cv2_compat.version))

        if (cv2_compat.version < [4, 4, 0] and
                match_parameters.match_method not in (
                    MatchMethod.SQDIFF, MatchMethod.CCORR_NORMED)):
            # See `matchTemplateMask`:
            # https://github.com/opencv/opencv/blob/3.2.0/modules/imgproc/src/templmatch.cpp#L840-L917
            raise ValueError(
                "Reference image %s has alpha channel, but transparency "
                "support requires match_method SQDIFF or CCORR_NORMED "
                "(you specified %s)."
                % (t.relative_filename, match_parameters.match_method))

    input_region = _validate_region(frame, region)
    if input_region.height < t.shape[0] or input_region.width < t.shape[1]:
        raise ValueError("%r must be larger than reference image %r"
                         % (input_region, t.shape))

    draw_source_region(frame, input_region)
    imglog = ImageLogger(
        "match", match_parameters=match_parameters,
        template_name=t.filename or "<Image>",
        region=input_region)
    imglog.imwrite("source", frame)

    try:
        for (matched, match_region, first_pass_matched,
             first_pass_certainty) in _find_matches(
                crop(frame, input_region), t, match_parameters, imglog):

            match_region = Region.from_extents(*match_region) \
                                 .translate(input_region)
            result = MatchResult(
                getattr(frame, "time", None), matched, match_region,
                first_pass_certainty, frame, t, first_pass_matched)
            imglog.append(matches=result)
            draw_on(frame, result, label="match(%s)" % (
                "<Image>" if t.relative_filename is None else
                repr(to_unicode(t.relative_filename))))
            yield result

    finally:
        try:
            _log_match_image_debug(imglog)
        except Exception:  # pylint:disable=broad-except
            pass


def wait_for_match(
    image: ImageT,
    timeout_secs: float = 10,
    consecutive_matches: int = 1,
    match_parameters: Optional[MatchParameters] = None,
    region: Region = Region.ALL,
    frames: Optional[Iterator[FrameT]] = None,
) -> MatchResult:
    """Search for an image in the device-under-test's video stream.

    :param image: The image to search for. See `match`.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. This function will raise `MatchTimeout` if no
        match is found within this time.

    :param int consecutive_matches:
        Forces this function to wait for several consecutive frames with a
        match found at the same x,y position. Increase ``consecutive_matches``
        to avoid false positives due to noise, or to wait for a moving
        selection to stop moving.

    :param match_parameters: See `match`.
    :param region: See `match`.

    :type frames: Iterator[stbt.Frame]
    :param frames: An iterable of video-frames to analyse. Defaults to
        ``stbt.frames()``.

    :returns: `MatchResult` when the image is found.
    :raises: `MatchTimeout` if no match is found after ``timeout_secs`` seconds.
    """
    if match_parameters is None:
        match_parameters = MatchParameters()

    if frames is None:
        import stbt_core
        frames = stbt_core.frames(timeout_secs=timeout_secs)
    else:
        frames = limit_time(frames, timeout_secs)

    match_count = 0
    last_pos = Position(0, 0)
    image = load_image(image)
    debug("Searching for " + (image.relative_filename or "<Image>"))
    for frame in frames:
        res = match(image, match_parameters=match_parameters,
                    region=region, frame=frame)
        if res.match and (match_count == 0 or res.position == last_pos):
            match_count += 1
        else:
            match_count = 0
        last_pos = res.position
        if match_count == consecutive_matches:
            debug("Matched " + (image.relative_filename or "<Image>"))
            return res

    raise MatchTimeout(res.frame, image.relative_filename, timeout_secs)


class MatchTimeout(UITestFailure):
    """Exception raised by `wait_for_match`.

    :ivar Frame screenshot: The last video frame that `wait_for_match` checked
        before timing out.

    :ivar str expected: Filename of the image that was being searched for.

    :vartype timeout_secs: int or float
    :ivar timeout_secs: Number of seconds that the image was searched for.
    """
    def __init__(self, screenshot: FrameT, expected: str|None,
                 timeout_secs: float):
        super().__init__()
        self.screenshot: FrameT = screenshot
        self.expected: str|None = expected
        self.timeout_secs: float = timeout_secs

    def __str__(self):
        return "Didn't find match for '%s' within %g seconds." % (
            self.expected, self.timeout_secs)


@memoize_iterator({"version": "33"})
def _find_matches(image, template, match_parameters, imglog):
    """Our image-matching algorithm.

    Runs 2 passes: `_find_candidate_matches` to locate potential matches, then
    `_confirm_match` to discard false positives from the first pass.

    Returns an iterator yielding zero or more `(True, position, certainty)`
    tuples for each location where `template` is found within `image`, followed
    by a single `(False, position, certainty)` tuple when there are no further
    matching locations.
    """

    for i, first_pass_matched, region, first_pass_certainty in \
            _find_candidate_matches(image, template, match_parameters, imglog):
        confirmed = (
            first_pass_matched and
            _confirm_match(image, region, template, match_parameters,
                           imwrite=lambda name, img: imglog.imwrite(
                               "match%d-%s" % (i, name), img)))  # pylint:disable=cell-var-from-loop

        yield (confirmed, list(region), first_pass_matched,
               first_pass_certainty)
        if not confirmed:
            break


def _find_candidate_matches(image, template, match_parameters, imglog):
    """First pass: Search for `template` in the entire `image`.

    This searches the entire image, so speed is more important than accuracy.
    False positives are ok; we apply a second pass later (`_confirm_match`) to
    weed out false positives.

    http://docs.opencv.org/modules/imgproc/doc/object_detection.html
    http://opencv-code.com/tutorials/fast-template-matching-with-image-pyramid
    """

    imglog.imwrite("template", template)
    imglog.set(template_shape=template.shape)
    if template.shape[2] == 4:
        imglog.imwrite("mask", template[:, :, 3])

    ddebug("Original image %s, template %s" % (image.shape, template.shape))

    method = {
        MatchMethod.SQDIFF: cv2.TM_SQDIFF,
        MatchMethod.SQDIFF_NORMED: cv2.TM_SQDIFF_NORMED,
        MatchMethod.CCORR_NORMED: cv2.TM_CCORR_NORMED,
        MatchMethod.CCOEFF_NORMED: cv2.TM_CCOEFF_NORMED,
    }[match_parameters.match_method]

    levels = get_config("match", "pyramid_levels", type_=int)
    if levels <= 0:
        raise ConfigurationError("'match.pyramid_levels' must be > 0")

    if (match_parameters.match_method == MatchMethod.SQDIFF and
            template.shape[:2] == image.shape[:2]):
        # Fast-path: image and template are the same size, skip pyramid, FFT,
        # etc.  This is particularly useful for full-image matching.
        ddebug("stbt-match: frame and template sizes match: Using fast-path")
        imglog.set(fast_path=True)
        s, n = sqdiff(template, image)
        if n == 0:
            certainty = 1
        else:
            certainty = 1 - float(s) / (n * 255 * 255)
        yield (0, certainty >= match_parameters.match_threshold,
               _image_region(image), certainty)
        yield (0, False, _image_region(image), 0.)
        return

    if template.shape[2] == 4:
        # OpenCV wants mask to match template's number of channels
        mask = cv2.cvtColor(template[:, :, 3], cv2.COLOR_GRAY2BGR)
        template = template[:, :, 0:3]
    else:
        mask = None

    mask_pyramid = _build_pyramid(mask, levels, is_mask=True)
    template_pyramid = _build_pyramid(template, len(mask_pyramid),
                                      is_template=True)
    image_pyramid = _build_pyramid(image, len(template_pyramid))
    roi_mask = None  # Initial region of interest: The whole image.

    for level in reversed(range(len(image_pyramid))):
        if roi_mask is not None:
            if any(x < 3 for x in roi_mask.shape):
                roi_mask = None
            else:
                roi_mask = cv2.pyrUp(roi_mask)

        def imwrite(name, img, scale=1):
            imglog.imwrite("level%d-%s" % (level, name), img, scale=scale)  # pylint:disable=cell-var-from-loop

        heatmap, heatmap_scale = _match_template(
            image_pyramid[level], template_pyramid[level], mask_pyramid[level],
            method, roi_mask, level, imwrite)

        # Relax the threshold slightly for scaled-down pyramid levels to
        # compensate for scaling artifacts.
        if level == 0:
            relax = 0
        elif match_parameters.match_method == MatchMethod.SQDIFF:
            relax = 0.02
        else:
            relax = 0.2
        threshold = max(0, match_parameters.match_threshold - relax)

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, heatmap_scale, threshold, level)
        imglog.append(pyramid_levels=(
            matched, best_match_position, certainty, level))

        if not matched:
            break

        if level > 0 or imglog.enabled:
            _, roi_mask = cv2.threshold(
                heatmap,
                (1 - threshold) * heatmap_scale,
                255,
                cv2.THRESH_BINARY_INV)
            roi_mask = roi_mask.astype(numpy.uint8)
            imwrite("source_matchtemplate_threshold", roi_mask)

    # pylint:disable=undefined-loop-variable
    region = Region(*_upsample(best_match_position, level),
                    width=template.shape[1], height=template.shape[0])

    for i in itertools.count():

        imglog.imwrite("match%d-heatmap" % i, heatmap, scale=heatmap_scale)
        yield (i, matched, region, certainty)
        if not matched:
            return
        assert level == 0

        # Exclude any positions that would overlap the previous match, then
        # keep iterating until we don't find any more matches.
        exclude = region.extend(x=-(region.width - 1), y=-(region.height - 1))
        cv2.rectangle(
            heatmap,
            # -1 because cv2.rectangle considers the bottom-right point to be
            # *inside* the rectangle.
            (exclude.x, exclude.y), (exclude.right - 1, exclude.bottom - 1),
            heatmap_scale,
            cv2_compat.FILLED)

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, heatmap_scale, threshold, level)
        region = Region(*best_match_position,
                        width=template.shape[1], height=template.shape[0])


def _match_template(image, template, mask, method, roi_mask, level, imwrite):

    ddebug("Level %d: image %s, template %s" % (
        level, image.shape, template.shape))

    heatmap_shape = (image.shape[0] - template.shape[0] + 1,
                     image.shape[1] - template.shape[1] + 1)
    NO_MATCH = {
        cv2.TM_SQDIFF: template.size * (255 ** 2),
        cv2.TM_SQDIFF_NORMED: 1,
        cv2.TM_CCORR_NORMED: 0,
        cv2.TM_CCOEFF_NORMED: 0,
    }
    matches_heatmap = numpy.full(heatmap_shape, NO_MATCH[method],
                                 dtype=numpy.float32)

    if roi_mask is None:
        # Initial region of interest: The whole image.
        rois = [_image_region(matches_heatmap)]
    else:
        ddebug("Level %d: roi_mask=%r, matches_heatmap=%r" % (
            level, roi_mask.shape, matches_heatmap.shape))

        # roi_mask comes from the previous pyramid level so it has gone through
        # pyrDown -> pyrUp. If the starting size was odd-numbered then after
        # this round-trip you end up with a size 1 pixel larger than the
        # original. We can discard the extra pixel safely because pyrUp blurs
        # with a 5x5 kernel after upscaling, so in effect it is dilating all
        # our ROIs by 1 pixel.
        roi_mask = crop(roi_mask, _image_region(matches_heatmap))

        rois = [Region(*x) for x in cv2_compat.find_contour_boxes(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)]
        _merge_regions(rois)

    if get_debug_level() > 1:
        source_with_rois = image.copy()
        for roi in rois:
            r = roi
            t = _Size(*template.shape[:2])
            s = _Size(*source_with_rois.shape[:2])
            cv2.rectangle(
                source_with_rois,
                (max(0, r.x), max(0, r.y)),
                (min(s.w - 1, r.right + t.w - 1),
                 min(s.h - 1, r.bottom + t.h - 1)),
                (0, 255, 255),
                thickness=1)
        imwrite("source_with_rois", source_with_rois)

    if mask is not None:
        kwargs = {"mask": mask}
    else:
        kwargs = {}  # For OpenCV < 3.0.0
    for roi in rois:
        r = roi.extend(right=template.shape[1] - 1,
                       bottom=template.shape[0] - 1)
        ddebug("Level %d: Searching in %s" % (level, r))
        cv2.matchTemplate(
            image[r.to_slice()],
            template,
            method,
            matches_heatmap[roi.to_slice()],
            **kwargs)

    if method == cv2.TM_SQDIFF:
        # OpenCV's SQDIFF_NORMED normalises by the pixel intensity across
        # the reference image and the source image patch. This doesn't work
        # at all for completely black images, and it exaggerates
        # differences for dark images. With SQDIFF we do our own
        # normalisation based solely on the number of pixels in the sum.
        # We still get a number between 0 - 1.

        if mask is not None:
            if cv2_compat.version < [4, 4, 0]:
                # matchTemplateMask normalises source & template image to [0,1].
                # https://github.com/opencv/opencv/blob/3.2.0/modules/imgproc/src/templmatch.cpp#L840-L917
                scale = max(1, numpy.count_nonzero(mask))
            else:
                scale = max(1, numpy.count_nonzero(mask)) * (255 ** 2)
        else:
            scale = template.size * (255 ** 2)
    else:
        scale = 1

    if method in (cv2.TM_CCORR_NORMED, cv2.TM_CCOEFF_NORMED):
        matches_heatmap = 1 - matches_heatmap

    imwrite("source", image)
    imwrite("template", template)
    imwrite("mask", mask)
    imwrite("source_matchtemplate", matches_heatmap, scale=scale)

    return matches_heatmap, scale


def _find_best_match_position(matches_heatmap, scale, threshold, level):
    min_value, _, min_location, _ = cv2.minMaxLoc(matches_heatmap)
    min_value /= scale
    certainty = 1 - min_value
    best_match_position = Position(*min_location)
    matched = certainty >= threshold
    ddebug("Level %d: %s at %s with certainty %s" % (
        level, "Matched" if matched else "Didn't match",
        best_match_position, certainty))
    return (matched, best_match_position, certainty)


def _build_pyramid(image, levels, is_template=False, is_mask=False):
    """A "pyramid" is [an image, the same image at 1/2 the size, at 1/4, ...]

    As a performance optimisation, image processing algorithms work on a
    "pyramid" by first identifying regions of interest (ROIs) in the smallest
    image; if results are positive, they proceed to the next larger image, etc.
    See http://docs.opencv.org/doc/tutorials/imgproc/pyramids/pyramids.html

    The original-sized image is called "level 0", the next smaller image "level
    1", and so on. This numbering corresponds to the index of the "pyramid"
    array.
    """
    if image is None:
        return [None] * levels
    pyramid = [image]
    previous = image
    for _ in range(levels - 1):
        if any(x < 20 for x in previous.shape[:2]):
            break
        downsampled = cv2.pyrDown(previous, borderType=cv2.BORDER_REPLICATE)
        if is_mask:
            cv2.threshold(downsampled, 254, 255, cv2.THRESH_BINARY, downsampled)
        previous = downsampled
        if is_template or is_mask:
            # Ignore pixels on the edge of the template, because pyrDown's
            # blurring will affect them differently than the corresponding
            # pixels in the frame (which do have neighbours, unlike the
            # template's edge pixels).
            downsampled = downsampled[1:-1, 1:-1]
        else:
            # ...and adjust the coordinate system of the match positions we're
            # returning accordingly. Because of the cropping, match position
            # 0,0 means pixel 1,1 of the template matched at pixel 1,1 of
            # the frame (this is the same as saying pixel 0,0 of the template
            # matched at pixel 0,0 of the frame, so we won't need to adjust
            # the match position afterwards).
            downsampled = downsampled[1:, 1:]
        if is_mask and numpy.count_nonzero(downsampled) // 3 < 400:
            break
        pyramid.append(downsampled)
    return pyramid


def _upsample(position, levels):
    """Convert position coordinates by the given number of pyramid levels.

    There is a loss of precision (unless ``levels`` is 0, in which case this
    function is a no-op).
    """
    return Position(position.x * 2 ** levels, position.y * 2 ** levels)


# Order of parameters consistent with OpenCV's ``numpy.ndarray.shape``.
class _Size(namedtuple("_Size", "h w")):
    pass


def _confirm_match(image, region, template, match_parameters, imwrite):
    """Second pass: Confirm that `template` matches `image` at `region`.

    This only checks `template` at a single position within `image`, so we can
    afford to do more computationally-intensive checks than
    `_find_candidate_matches`.
    """

    if match_parameters.confirm_method == ConfirmMethod.NONE:
        return True

    if template.shape[2] == 4:
        # Create transparency mask from alpha channel
        mask = template[:, :, 3]
        template = template[:, :, 0:3]
    else:
        mask = None

    # Set Region Of Interest to the "best match" location
    image = image[region.y:region.bottom, region.x:region.right]
    imwrite("confirm-source_roi", image)
    if image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    imwrite("confirm-source_roi_gray", image)
    imwrite("confirm-template_gray", template)

    if match_parameters.confirm_method == ConfirmMethod.NORMED_ABSDIFF:
        cv2.normalize(image, image, 0, 255, cv2.NORM_MINMAX, mask=mask)
        cv2.normalize(template, template, 0, 255, cv2.NORM_MINMAX, mask=mask)
        imwrite("confirm-source_roi_gray_normalized", image)
        imwrite("confirm-template_gray_normalized", template)

    if mask is not None:
        image = cv2.bitwise_and(image, mask)
        template = cv2.bitwise_and(template, mask)
        imwrite("confirm-source_roi_masked", image)
        imwrite("confirm-template_masked", template)

    absdiff = cv2.absdiff(image, template)
    _, thresholded = cv2.threshold(
        absdiff, int((1 - match_parameters.confirm_threshold) * 255),
        255, cv2.THRESH_BINARY)
    eroded = cv2.erode(
        thresholded,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=match_parameters.erode_passes)
    imwrite("confirm-absdiff", absdiff)
    imwrite("confirm-absdiff_threshold", thresholded)
    imwrite("confirm-absdiff_threshold_erode", eroded)

    return cv2.countNonZero(eroded) == 0


def _merge_regions(regions):
    """Discard regions that are entirely contained within another region."""
    regions.sort(key=lambda r: r.width * r.height)
    i = len(regions) - 1
    while i > 0:
        r = regions[i]
        for j in range(i - 1, -1, -1):
            if r.contains(regions[j]):
                del regions[j]
                i -= 1
        i -= 1


def _log_match_image_debug(imglog):
    if not imglog.enabled:
        return

    title = "stbt.match(%r): %s" % (
        imglog.data["template_name"],
        "Matched" if any(imglog.data["matches"]) else "Didn't match")

    for matched, position, _, level in imglog.data.get("pyramid_levels", []):
        template = imglog.images["level%d-template" % level]
        imglog.imwrite("level%d-source_with_match" % level,
                       imglog.images["level%d-source" % level],
                       Region(x=position.x, y=position.y,
                              width=template.shape[1],
                              height=template.shape[0]),
                       _Annotation.MATCHED if matched else _Annotation.NO_MATCH)

    for i, result in enumerate(imglog.data["matches"]):
        imglog.imwrite(
            "match%d-source_with_match" % i, imglog.images["source"],
            result.region, _Annotation.MATCHED if result._first_pass_matched
            else _Annotation.NO_MATCH)

    template = """\
        <h4>{{title}}</h4>

        {{ annotated_image(matches) }}

        <h5>First pass (find candidate matches):</h5>

        <p>Searching for <b>template</b> {{link("template")}}
            {% if "mask" in images %}
            with <b>transparency mask</b> {{link("mask")}}
            {% endif %}
            within <b>source</b> image {{link("source")}}</p>

        {% if fast_path %}
        <p>Taking fast path - template shape <code>{{ template_shape }}</code>
        matches size of target region <code>{{ region }}</code></p>

        <table class="table">
        <tr>
          <th>Match #</th>
          <th><b>Matched?<b></th>
          <th><b>certainty</b></th>
        </tr>
        {% for m in matches %}
        {# note that loop.index is 1-based #}
        <tr>
          <td><b>{{loop.index}}</b></td>
          <td>{{"Matched" if m._first_pass_matched else "Didn't match"}}</td>
          <td>{{"%.4f"|format(m.first_pass_result)}}</td>
        </tr>
        {% endfor %}
        </table>
        {% else %}
        <table class="table">
        <tr>
          <th>Pyramid level</th>
          <th>Match #</th>
          <th>Searching for <b>template</b></th>
          <th>within <b>source regions of interest</b></th>
          <th>
            OpenCV <b>matchTemplate heatmap</b>
            with {{match_parameters.match_method}}
            (darkest pixel indicates position of best match).
          </th>
          <th>
            matchTemplate heatmap <b>above match_threshold</b>
            of {{"%g"|format(match_parameters.match_threshold)}}
            (white pixels indicate positions above the threshold).
          </th>
          <th><b>Matched?<b></th>
          <th>Best match <b>position</b></th>
          <th>&nbsp;</th>
          <th><b>certainty</b></th>
        </tr>

        {% for matched, position, certainty, level in pyramid_levels %}
        <tr>
          <td><b>{{level}}</b></td>
          <td><b>{{"0" if level == 0 else ""}}</b></td>
          <td>
            {{link("template", level)}}
            {% if "mask" in images %}
            {{link("mask", level)}}
            {% endif %}
          </td>
          <td>{{link("source_with_rois", level)}}</td>
          <td>{{link("source_matchtemplate", level)}}</td>
          <td>
            {{link("source_matchtemplate_threshold", level) if matched else ""}}
          </td>
          <td>{{"Matched" if matched else "Didn't match"}}</td>
          <td>{{position if level > 0 else matches[0].region}}</td>
          <td>{{link("source_with_match", level)}}</td>
          <td>{{"%.4f"|format(certainty)}}</td>
        </tr>
        {% endfor %}

        {% for m in matches[1:] %}
        {# note that loop.index is 1-based #}
        <tr>
          <td>&nbsp;</td>
          <td><b>{{loop.index}}</b></td>
          <td>&nbsp;</td>
          <td>&nbsp;</td>
          <td>{{link("heatmap", match=loop.index)}}</td>
          <td></td>
          <td>{{"Matched" if m._first_pass_matched else "Didn't match"}}</td>
          <td>{{m.region}}</td>
          <td>{{link("source_with_match", match=loop.index)}}</td>
          <td>{{"%.4f"|format(m.first_pass_result)}}</td>
        </tr>
        {% endfor %}

        </table>
        {% endif %}

        {% if show_second_pass %}
          <h5>Second pass (confirmation):</h5>

          <p><b>Confirm method:</b> {{match_parameters.confirm_method}}</p>

          {% if match_parameters.confirm_method != ConfirmMethod.NONE %}
            <table class="table">
            <tr>
              <th>Match #</th>
              <th>Comparing <b>template</b></th>
              <th>against <b>source image's region of interest</b></th>
              {% if match_parameters.confirm_method ==
                         ConfirmMethod.NORMED_ABSDIFF %}
                <th><b>Normalised template</b></th>
                <th><b>Normalised source</b></th>
              {% endif %}
              <th><b>Absolute differences</b></th>
              <th>
                Differences <b>above confirm_threshold</b>
                of {{"%.2f"|format(match_parameters.confirm_threshold)}}
              </th>
              <th>
                After <b>eroding</b>
                {{match_parameters.erode_passes}}
                {{"time" if match_parameters.erode_passes == 1
                  else "times"}};
                the template matches if no differences (white pixels) remain
              </th>
            </tr>

            {% for m in matches %}
              {% if m._first_pass_matched %}
                <tr>
                  <td><b>{{loop.index0}}</b></td>
                  <td>{{link("confirm-template_gray", match=0)}}</td>
                  <td>{{link("confirm-source_roi_gray", match=loop.index0)}}</td>
                  {% if match_parameters.confirm_method ==
                             ConfirmMethod.NORMED_ABSDIFF %}
                    <td>{{link("confirm-template_gray_normalized", match=loop.index0)}}</td>
                    <td>{{link("confirm-source_roi_gray_normalized", match=loop.index0)}}</td>
                  {% endif %}
                  <td>{{link("confirm-absdiff", match=loop.index0)}}</td>
                  <td>{{link("confirm-absdiff_threshold", match=loop.index0)}}</td>
                  <td>{{link("confirm-absdiff_threshold_erode", match=loop.index0)}}</td>
                </tr>
              {% endif %}
            {% endfor %}

            </table>
          {% endif %}
        {% endif %}
    """

    def link(name, level=None, match=None):  # pylint: disable=redefined-outer-name
        return ("<a href='{0}{1}{2}.png'><img src='{0}{1}{2}.png'"
                " class='thumb'></a>"
                .format("" if level is None else "level%d-" % level,
                        "" if match is None else "match%d-" % match,
                        name))

    imglog.html(
        template,
        ConfirmMethod=ConfirmMethod,
        fast_path=imglog.data.get("fast_path"),
        link=link,
        MatchMethod=MatchMethod,
        show_second_pass=any(
            x._first_pass_matched for x in imglog.data["matches"]),
        title=title,
    )
