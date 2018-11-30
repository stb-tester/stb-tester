# coding: utf-8

"""
Copyright 2012-2014 YouView TV Ltd and contributors.
Copyright 2013-2018 stb-tester.com Ltd.

License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import itertools
import os
from collections import namedtuple

import cv2
import numpy

import _stbt.cv2_compat

from .config import ConfigurationError, get_config
from .imgproc_cache import memoize_iterator
from .imgutils import _frame_repr, _image_region, _load_image, crop, limit_time
from .logging import ddebug, debug, draw_on, get_debug_level, ImageLogger
from .types import Region, UITestFailure


class MatchParameters(object):
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

    :param str match_method:
      The method to be used by the first pass of stb-tester's image matching
      algorithm, to find the most likely location of the reference image
      within the larger source image.

      Allowed values are "sqdiff-normed", "ccorr-normed", and "ccoeff-normed".
      For the meaning of these parameters, see OpenCV's
      :ocv:pyfunc:`cv2.matchTemplate`.

      We recommend that you don't change this from its default value of
      "sqdiff-normed".

    :param float match_threshold:
      How strong a result from the first pass must be, to be considered a
      match. Valid values range from 0 (anything is considered to match)
      to 1 (the match has to be pixel perfect). This defaults to 0.8.

    :param str confirm_method:
      The method to be used by the second pass of stb-tester's image matching
      algorithm, to confirm that the region identified by the first pass is a
      good match.

      The first pass often gives false positives (it reports a "match" for an
      image that shouldn't match). The second pass is more CPU-intensive, but
      it only checks the position of the image that the first pass identified.
      The allowed values are:

      :"none":
        Do not confirm the match. Assume that the potential match found is
        correct.

      :"absdiff":
        Compare the absolute difference of each pixel from the reference image
        against its counterpart from the candidate region in the source video
        frame.

      :"normed-absdiff":
        Normalise the pixel values from both the reference image and the
        candidate region in the source video frame, then compare the absolute
        difference as with "absdiff".

        This gives better results with low-contrast images. We recommend setting
        this as the default `confirm_method` in stbt.conf, with a
        `confirm_threshold` of 0.30.

    :param float confirm_threshold:
      The maximum allowed difference between any given pixel from the reference
      image and its counterpart from the candidate region in the source video
      frame, as a fraction of the pixel's total luminance range.

      Valid values range from 0 (more strict) to 1.0 (less strict).
      Useful values tend to be around 0.16 for the "absdiff" method, and 0.30
      for the "normed-absdiff" method.

    :param int erode_passes:
      After the "absdiff" or "normed-absdiff" absolute difference is taken,
      stb-tester runs an erosion algorithm that removes single-pixel differences
      to account for noise. Useful values are 1 (the default) and 0 (to disable
      this step).

    """

    def __init__(self, match_method=None, match_threshold=None,
                 confirm_method=None, confirm_threshold=None,
                 erode_passes=None):
        if match_method is None:
            match_method = get_config('match', 'match_method')
        if match_threshold is None:
            match_threshold = get_config(
                'match', 'match_threshold', type_=float)
        if confirm_method is None:
            confirm_method = get_config('match', 'confirm_method')
        if confirm_threshold is None:
            confirm_threshold = get_config(
                'match', 'confirm_threshold', type_=float)
        if erode_passes is None:
            erode_passes = get_config('match', 'erode_passes', type_=int)

        if match_method not in (
                "sqdiff-normed", "ccorr-normed", "ccoeff-normed"):
            raise ValueError("Invalid match_method '%s'" % match_method)
        if confirm_method not in ("none", "absdiff", "normed-absdiff"):
            raise ValueError("Invalid confirm_method '%s'" % confirm_method)

        self.match_method = match_method
        self.match_threshold = match_threshold
        self.confirm_method = confirm_method
        self.confirm_threshold = confirm_threshold
        self.erode_passes = erode_passes

    def __repr__(self):
        return (
            "MatchParameters(match_method=%r, match_threshold=%r, "
            "confirm_method=%r, confirm_threshold=%r, erode_passes=%r)"
            % (self.match_method, self.match_threshold,
               self.confirm_method, self.confirm_threshold, self.erode_passes))


class Position(namedtuple('Position', 'x y')):
    """A point within the video frame.

    `x` and `y` are integer coordinates (measured in number of pixels) from the
    top left corner of the video frame.
    """
    pass


class MatchResult(object):
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

    :ivar image: The reference image that was searched for, as given to `match`.
    """
    _fields = ("time", "match", "region", "first_pass_result", "frame", "image")

    def __init__(
            self, time, match, region,  # pylint: disable=redefined-outer-name
            first_pass_result, frame, image, _first_pass_matched=None):
        self.time = time
        self.match = match
        self.region = region
        self.first_pass_result = first_pass_result
        self.frame = frame
        self.image = image
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
                "<Custom Image>" if isinstance(self.image, numpy.ndarray)
                else repr(self.image)))

    def __nonzero__(self):
        return self.match

    @property
    def position(self):
        return Position(self.region.x, self.region.y)


def match(image, frame=None, match_parameters=None, region=Region.ALL):
    """
    Search for an image in a single video frame.

    :type image: string or `numpy.ndarray`
    :param image:
      The image to search for. It can be the filename of a png file on disk, or
      a numpy array containing the pixel data in 8-bit BGR format.

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


def match_all(image, frame=None, match_parameters=None, region=Region.ALL):
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


def _match_all(image, frame, match_parameters, region):
    """
    Generator that yields a sequence of zero or more truthy MatchResults,
    followed by a falsey MatchResult.
    """
    if match_parameters is None:
        match_parameters = MatchParameters()

    template = _load_image(image)

    if frame is None:
        import stbt
        frame = stbt.get_frame()

    imglog = ImageLogger(
        "match", match_parameters=match_parameters,
        template_name=template.friendly_name)

    region = Region.intersect(_image_region(frame), region)

    # pylint:disable=undefined-loop-variable
    try:
        for (matched, match_region, first_pass_matched,
             first_pass_certainty) in _find_matches(
                crop(frame, region), template.image,
                match_parameters, imglog):

            match_region = Region.from_extents(*match_region) \
                                 .translate(region.x, region.y)
            result = MatchResult(
                getattr(frame, "time", None), matched, match_region,
                first_pass_certainty, frame,
                (template.relative_filename or template.image),
                first_pass_matched)
            imglog.append(matches=result)
            draw_on(frame, result, label="match(%r)" %
                    os.path.basename(template.friendly_name))
            yield result

    finally:
        try:
            _log_match_image_debug(imglog)
        except Exception:  # pylint:disable=broad-except
            pass


def detect_match(image, timeout_secs=10, match_parameters=None,
                 region=Region.ALL, frames=None):
    """Generator that yields a sequence of one `MatchResult` for each frame
    processed from the device-under-test's video stream.

    :param image: See `match`.

    :type timeout_secs: int or float or None
    :param timeout_secs:
        A timeout in seconds. After this timeout the iterator will be exhausted.
        If ``timeout_secs`` is ``None`` then the iterator will yield frames
        forever. Note that you can stop iterating (for example with ``break``)
        at any time.

    :param match_parameters: See `match`.
    :param region: See `match`.

    :type frames: Iterator[stbt.Frame]
    :param frames: An iterable of video-frames to analyse. Defaults to
        ``stbt.frames()``.
    """
    if frames is None:
        import stbt
        frames = stbt.frames(timeout_secs=timeout_secs)
    else:
        frames = limit_time(frames, timeout_secs)

    template = _load_image(image)

    debug("Searching for " + template.friendly_name)

    for frame in frames:
        result = match(
            template, frame=frame, match_parameters=match_parameters,
            region=region)
        draw_on(frame, result, label="match(%r)" %
                os.path.basename(template.friendly_name))
        yield result


def wait_for_match(image, timeout_secs=10, consecutive_matches=1,
                   match_parameters=None, region=Region.ALL, frames=None):
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

    match_count = 0
    last_pos = Position(0, 0)
    image = _load_image(image)
    for res in detect_match(
            image, timeout_secs, match_parameters=match_parameters,
            region=region, frames=frames):
        if res.match and (match_count == 0 or res.position == last_pos):
            match_count += 1
        else:
            match_count = 0
        last_pos = res.position
        if match_count == consecutive_matches:
            debug("Matched " + image.friendly_name)
            return res

    raise MatchTimeout(res.frame, image.friendly_name, timeout_secs)  # pylint:disable=undefined-loop-variable


class MatchTimeout(UITestFailure):
    """Exception raised by `wait_for_match`.

    :ivar Frame screenshot: The last video frame that `wait_for_match` checked
        before timing out.

    :ivar str expected: Filename of the image that was being searched for.

    :vartype timeout_secs: int or float
    :ivar timeout_secs: Number of seconds that the image was searched for.
    """
    def __init__(self, screenshot, expected, timeout_secs):
        super(MatchTimeout, self).__init__()
        self.screenshot = screenshot
        self.expected = expected
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find match for '%s' within %g seconds." % (
            self.expected, self.timeout_secs)


@memoize_iterator({"version": "25"})
def _find_matches(image, template, match_parameters, imglog):
    """Our image-matching algorithm.

    Runs 2 passes: `_find_candidate_matches` to locate potential matches, then
    `_confirm_match` to discard false positives from the first pass.

    Returns an iterator yielding zero or more `(True, position, certainty)`
    tuples for each location where `template` is found within `image`, followed
    by a single `(False, position, certainty)` tuple when there are no further
    matching locations.
    """

    if any(image.shape[x] < template.shape[x] for x in (0, 1)):
        raise ValueError("Source image must be larger than reference image")
    if any(template.shape[x] < 1 for x in (0, 1)):
        raise ValueError("Reference image must contain some data")
    if not (len(template.shape) == 2 or
            len(template.shape) == 3 and template.shape[2] == 3):
        raise ValueError("Reference image must be grayscale or 3 channel BGR")
    if (len(image.shape) != len(template.shape) or
            len(image.shape) == 3 and image.shape[2] != template.shape[2]):
        raise ValueError(
            "Source and reference images must have the same number of channels")
    if template.dtype != numpy.uint8:
        raise ValueError("Reference image must be 8-bits per channel")

    # pylint:disable=undefined-loop-variable
    for i, first_pass_matched, region, first_pass_certainty in \
            _find_candidate_matches(image, template, match_parameters,
                                    imglog):
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

    imglog.imwrite("source", image)
    imglog.imwrite("template", template)
    ddebug("Original image %s, template %s" % (image.shape, template.shape))

    method = {
        'sqdiff-normed': cv2.TM_SQDIFF_NORMED,
        'ccorr-normed': cv2.TM_CCORR_NORMED,
        'ccoeff-normed': cv2.TM_CCOEFF_NORMED,
    }[match_parameters.match_method]

    levels = get_config("match", "pyramid_levels", type_=int)
    if levels <= 0:
        raise ConfigurationError("'match.pyramid_levels' must be > 0")
    template_pyramid = _build_pyramid(template, levels)
    image_pyramid = _build_pyramid(image, len(template_pyramid))
    roi_mask = None  # Initial region of interest: The whole image.

    for level in reversed(range(len(template_pyramid))):
        if roi_mask is not None:
            if any(x < 3 for x in roi_mask.shape):
                roi_mask = None
            else:
                roi_mask = cv2.pyrUp(roi_mask)

        def imwrite(name, img):
            imglog.imwrite("level%d-%s" % (level, name), img)  # pylint:disable=cell-var-from-loop

        heatmap = _match_template(
            image_pyramid[level], template_pyramid[level], method,
            roi_mask, level, imwrite)

        # Relax the threshold slightly for scaled-down pyramid levels to
        # compensate for scaling artifacts.
        threshold = max(
            0,
            match_parameters.match_threshold - (0.2 if level > 0 else 0))

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, method, threshold, level)
        imglog.append(pyramid_levels=(
            matched, best_match_position, certainty, level))

        if not matched:
            break

        _, roi_mask = cv2.threshold(
            heatmap,
            ((1 - threshold) if method == cv2.TM_SQDIFF_NORMED else threshold),
            255,
            (cv2.THRESH_BINARY_INV if method == cv2.TM_SQDIFF_NORMED
             else cv2.THRESH_BINARY))
        roi_mask = roi_mask.astype(numpy.uint8)
        imwrite("source_matchtemplate_threshold", roi_mask)

    # pylint:disable=undefined-loop-variable
    region = Region(*_upsample(best_match_position, level),
                    width=template.shape[1], height=template.shape[0])

    for i in itertools.count():

        imglog.imwrite("match%d-heatmap" % i, heatmap)
        yield (i, matched, region, certainty)
        if not matched:
            return
        assert level == 0

        # Exclude any positions that would overlap the previous match, then
        # keep iterating until we don't find any more matches.
        exclude = region.extend(x=-(region.width - 1), y=-(region.height - 1))
        mask_value = (255 if match_parameters.match_method == 'sqdiff-normed'
                      else 0)
        cv2.rectangle(
            heatmap,
            # -1 because cv2.rectangle considers the bottom-right point to be
            # *inside* the rectangle.
            (exclude.x, exclude.y), (exclude.right - 1, exclude.bottom - 1),
            mask_value, _stbt.cv2_compat.FILLED)

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, method, threshold, level)
        region = Region(*best_match_position,
                        width=template.shape[1], height=template.shape[0])


def _match_template(image, template, method, roi_mask, level, imwrite):

    ddebug("Level %d: image %s, template %s" % (
        level, image.shape, template.shape))

    matches_heatmap = (
        (numpy.ones if method == cv2.TM_SQDIFF_NORMED else numpy.zeros)(
            (image.shape[0] - template.shape[0] + 1,
             image.shape[1] - template.shape[1] + 1),
            dtype=numpy.float32))

    if roi_mask is None:
        rois = [  # Initial region of interest: The whole image.
            _Rect(0, 0, matches_heatmap.shape[1], matches_heatmap.shape[0])]
    else:
        rois = [_Rect(*x) for x in _stbt.cv2_compat.find_contour_boxes(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)]

    if get_debug_level() > 1:
        source_with_rois = image.copy()
        for roi in rois:
            r = roi
            t = _Size(*template.shape[:2])
            s = _Size(*source_with_rois.shape[:2])
            cv2.rectangle(
                source_with_rois,
                (max(0, r.x), max(0, r.y)),
                (min(s.w - 1, r.x + r.w + t.w - 1),
                 min(s.h - 1, r.y + r.h + t.h - 1)),
                (0, 255, 255),
                thickness=1)
        imwrite("source_with_rois", source_with_rois)

    for roi in rois:
        r = roi.expand(_Size(*template.shape[:2])).shrink(_Size(1, 1))
        ddebug("Level %d: Searching in %s" % (level, roi))
        cv2.matchTemplate(
            image[r.to_slice()],
            template,
            method,
            matches_heatmap[roi.to_slice()])

    imwrite("source", image)
    imwrite("template", template)
    imwrite("source_matchtemplate", matches_heatmap)

    return matches_heatmap


def _find_best_match_position(matches_heatmap, method, threshold, level):
    min_value, max_value, min_location, max_location = cv2.minMaxLoc(
        matches_heatmap)
    if method == cv2.TM_SQDIFF_NORMED:
        certainty = (1 - min_value)
        best_match_position = Position(*min_location)
    elif method in (cv2.TM_CCORR_NORMED, cv2.TM_CCOEFF_NORMED):
        certainty = max_value
        best_match_position = Position(*max_location)
    else:
        raise ValueError("Invalid matchTemplate method '%s'" % method)

    matched = certainty >= threshold
    ddebug("Level %d: %s at %s with certainty %s" % (
        level, "Matched" if matched else "Didn't match",
        best_match_position, certainty))
    return (matched, best_match_position, certainty)


def _build_pyramid(image, levels):
    """A "pyramid" is [an image, the same image at 1/2 the size, at 1/4, ...]

    As a performance optimisation, image processing algorithms work on a
    "pyramid" by first identifying regions of interest (ROIs) in the smallest
    image; if results are positive, they proceed to the next larger image, etc.
    See http://docs.opencv.org/doc/tutorials/imgproc/pyramids/pyramids.html

    The original-sized image is called "level 0", the next smaller image "level
    1", and so on. This numbering corresponds to the array index of the
    "pyramid" array.
    """
    pyramid = [image]
    for _ in range(levels - 1):
        if any(x < 20 for x in pyramid[-1].shape[:2]):
            break
        pyramid.append(cv2.pyrDown(pyramid[-1]))
    return pyramid


def _upsample(position, levels):
    """Convert position coordinates by the given number of pyramid levels.

    There is a loss of precision (unless ``levels`` is 0, in which case this
    function is a no-op).
    """
    return Position(position.x * 2 ** levels, position.y * 2 ** levels)


# Order of parameters consistent with ``cv2.boundingRect``.
class _Rect(namedtuple("_Rect", "x y w h")):
    def expand(self, size):
        return _Rect(self.x, self.y, self.w + size.w, self.h + size.h)

    def shrink(self, size):
        return _Rect(self.x, self.y, self.w - size.w, self.h - size.h)

    def shift(self, position):
        return _Rect(self.x + position.x, self.y + position.y, self.w, self.h)

    def to_slice(self):
        """Return a 2-dimensional slice suitable for indexing a numpy array."""
        return (slice(self.y, self.y + self.h), slice(self.x, self.x + self.w))


# Order of parameters consistent with OpenCV's ``numpy.ndarray.shape``.
class _Size(namedtuple("_Size", "h w")):
    pass


def _confirm_match(image, region, template, match_parameters, imwrite):
    """Second pass: Confirm that `template` matches `image` at `region`.

    This only checks `template` at a single position within `image`, so we can
    afford to do more computationally-intensive checks than
    `_find_candidate_matches`.
    """

    if match_parameters.confirm_method == "none":
        return True

    # Set Region Of Interest to the "best match" location
    image = image[region.y:region.bottom, region.x:region.right]
    imwrite("confirm-source_roi", image)
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    imwrite("confirm-source_roi_gray", image)
    imwrite("confirm-template_gray", template)

    if match_parameters.confirm_method == "normed-absdiff":
        cv2.normalize(image, image, 0, 255, cv2.NORM_MINMAX)
        cv2.normalize(template, template, 0, 255, cv2.NORM_MINMAX)
        imwrite("confirm-source_roi_gray_normalized", image)
        imwrite("confirm-template_gray_normalized", template)

    absdiff = cv2.absdiff(image, template)
    _, thresholded = cv2.threshold(
        absdiff, int(match_parameters.confirm_threshold * 255),
        255, cv2.THRESH_BINARY)
    eroded = cv2.erode(
        thresholded,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=match_parameters.erode_passes)
    imwrite("confirm-absdiff", absdiff)
    imwrite("confirm-absdiff_threshold", thresholded)
    imwrite("confirm-absdiff_threshold_erode", eroded)

    return cv2.countNonZero(eroded) == 0


def _log_match_image_debug(imglog):
    if not imglog.enabled:
        return

    from _stbt.core import _Annotation

    for matched, position, _, level in imglog.data["pyramid_levels"]:
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
            result.region, _Annotation.MATCHED if result._first_pass_matched  # pylint:disable=protected-access
            else _Annotation.NO_MATCH)

    imglog.imwrite(
        "source_with_matches", imglog.images["source"],
        [x.region for x in imglog.data["matches"]],
        [_Annotation.MATCHED if x.match else _Annotation.NO_MATCH
         for x in imglog.data["matches"]])

    template = u"""\
        <h4>
            {{"Matched" if matched else "Didn't match"}}
            <i>{{template_name}}</i>
        </h4>

        <img src="source_with_matches.png" />

        <h5>First pass (find candidate matches):</h5>

        <p>Searching for <b>template</b> {{link("template")}}
            within <b>source</b> image {{link("source")}}

        <table class="table">
        <tr>
          <th>Pyramid level</th>
          <th>Match #</th>
          <th>Searching for <b>template</b></th>
          <th>within <b>source regions of interest</b></th>
          <th>
            OpenCV <b>matchTemplate heatmap</b>
            with method {{match_parameters.match_method}}
            ({{"darkest" if match_parameters.match_method ==
                    "sqdiff-normed" else "lightest"}}
            pixel indicates position of best match).
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
          <td>{{link("template", level)}}</td>
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

        {% if show_second_pass %}
          <h5>Second pass (confirmation):</h5>

          <p><b>Confirm method:</b> {{match_parameters.confirm_method}}</p>

          {% if match_parameters.confirm_method != "none" %}
            <table class="table">
            <tr>
              <th>Match #</th>
              <th>Comparing <b>template</b></th>
              <th>against <b>source image's region of interest</b></th>
              {% if match_parameters.confirm_method == "normed-absdiff" %}
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
                  {% if match_parameters.confirm_method == "normed-absdiff" %}
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

        <p>For further help please read
            <a href="http://stb-tester.com/match-parameters.html">stb-tester
            image matching parameters</a>.
    """

    def link(name, level=None, match=None):  # pylint: disable=redefined-outer-name
        return ("<a href='{0}{1}{2}.png'><img src='{0}{1}{2}.png'"
                " class='thumb'></a>"
                .format("" if level is None else "level%d-" % level,
                        "" if match is None else "match%d-" % match,
                        name))

    imglog.html(
        template,
        link=link,
        match_parameters=imglog.data["match_parameters"],
        matched=any(imglog.data["matches"]),
        matches=imglog.data["matches"],
        pyramid_levels=imglog.data["pyramid_levels"],
        show_second_pass=any(
            x._first_pass_matched for x in imglog.data["matches"]),  # pylint:disable=protected-access
        template_name=imglog.data["template_name"],
    )
