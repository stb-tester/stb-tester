# coding: utf-8

"""
Copyright 2012-2014 YouView TV Ltd and contributors.
Copyright 2013-2018 stb-tester.com Ltd.

License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import enum
import itertools
import os
from collections import namedtuple

import cv2
import numpy

from . import cv2_compat
from .config import ConfigurationError, get_config
from .imgproc_cache import memoize_iterator
from .imgutils import _frame_repr, _image_region, _load_image, crop, limit_time
from .logging import ddebug, debug, draw_on, get_debug_level, ImageLogger
from .types import Region, UITestFailure


class MatchMethod(enum.Enum):
    SQDIFF = "sqdiff"
    SQDIFF_NORMED = "sqdiff-normed"
    CCORR_NORMED = "ccorr-normed"
    CCOEFF_NORMED = "ccoeff-normed"

    # For nicer formatting in generated API documentation:
    def __repr__(self):
        return str(self)


class ConfirmMethod(enum.Enum):
    NONE = "none"
    ABSDIFF = "absdiff"
    NORMED_ABSDIFF = "normed-absdiff"

    # For nicer formatting in generated API documentation:
    def __repr__(self):
        return str(self)


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

    :type match_method: `MatchMethod`
    :param match_method:
      The method to be used by the first pass of stb-tester's image matching
      algorithm, to find the most likely location of the reference image within
      the larger source image. For details see OpenCV's
      :ocv:pyfunc:`cv2.matchTemplate`. Defaults to ``MatchMethod.SQDIFF``.

    :param float match_threshold:
      How strong a result from the first pass must be, to be considered a
      match. Valid values range from 0 (anything is considered to match)
      to 1 (the match has to be pixel perfect). This defaults to 0.8.

    :type confirm_method: `ConfirmMethod`
    :param confirm_method:
      The method to be used by the second pass of stb-tester's image matching
      algorithm, to confirm that the region identified by the first pass is a
      good match.

      The first pass often gives false positives (it reports a "match" for an
      image that shouldn't match). The second pass is more CPU-intensive, but
      it only checks the position of the image that the first pass identified.
      The allowed values are:

      :ConfirmMethod.NONE:
        Do not confirm the match. Assume that the potential match found is
        correct.

      :ConfirmMethod.ABSDIFF:
        Compare the absolute difference of each pixel from the reference image
        against its counterpart from the candidate region in the source video
        frame.

      :ConfirmMethod.NORMED_ABSDIFF:
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

    Added in v30: MatchMethod.SQDIFF, and support for transparency in the
    reference image.
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

    if frame is None:
        import stbt
        frame = stbt.get_frame()

    template = _load_image(image)
    t = template.image
    mask = None

    if len(t.shape) == 2 or t.shape[2] == 1 or t.shape[2] == 3:
        pass
    elif t.shape[2] == 4:
        # Create transparency mask from alpha channel
        mask = t[:, :, 3]
        mask[mask < 255] = 0
        # OpenCV wants mask to match template's number of channels
        mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        t = t[:, :, 0:3]
    else:
        raise ValueError("Expected 3-channel image, got %d channels: %s"
                         % (t.shape[2], template.absolute_filename))

    if any(frame.shape[x] < t.shape[x] for x in (0, 1)):
        raise ValueError("Frame %r must be larger than reference image %r"
                         % (frame.shape, t.shape))
    if any(t.shape[x] < 1 for x in (0, 1)):
        raise ValueError("Reference image %r must contain some data"
                         % (t.shape,))
    if (len(frame.shape) != len(t.shape) or
            len(frame.shape) == 3 and frame.shape[2] != t.shape[2]):
        raise ValueError(
            "Frame %r and reference image %r must have the same number of "
            "channels" % (frame.shape, t.shape))

    if mask is not None:
        if cv2_compat.version < [3, 0, 0]:
            raise ValueError(
                "Reference image %s has alpha channel, but transparency "
                "support requires OpenCV 3.0 or greater (you have %s)."
                % (template.relative_filename, cv2_compat.version))
        if match_parameters.match_method not in (MatchMethod.SQDIFF,
                                                 MatchMethod.CCORR_NORMED):
            # See `matchTemplateMask`:
            # https://github.com/opencv/opencv/blob/3.2.0/modules/imgproc/src/templmatch.cpp#L840-L917
            raise ValueError(
                "Reference image %s has alpha channel, but transparency "
                "support requires match_method SQDIFF or CCORR_NORMED "
                "(you specified %s)."
                % (template.relative_filename, match_parameters.match_method))

    imglog = ImageLogger(
        "match", match_parameters=match_parameters,
        template_name=template.friendly_name)

    input_region = Region.intersect(_image_region(frame), region)
    if input_region is None:
        raise ValueError("frame with dimensions %r doesn't contain %r"
                         % (frame.shape, region))

    # pylint:disable=undefined-loop-variable
    try:
        for (matched, match_region, first_pass_matched,
             first_pass_certainty) in _find_matches(
                crop(frame, input_region), t, mask,
                match_parameters, imglog):

            match_region = Region.from_extents(*match_region) \
                                 .translate(input_region.x, input_region.y)
            result = MatchResult(
                getattr(frame, "time", None), matched, match_region,
                max(0, first_pass_certainty), frame,
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

    if frames is None:
        import stbt
        frames = stbt.frames(timeout_secs=timeout_secs)
    else:
        frames = limit_time(frames, timeout_secs)

    match_count = 0
    last_pos = Position(0, 0)
    image = _load_image(image)
    debug("Searching for " + image.friendly_name)
    for frame in frames:
        res = match(image, match_parameters=match_parameters,
                    region=region, frame=frame)
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


@memoize_iterator({"version": "30"})
def _find_matches(image, template, mask, match_parameters, imglog):
    """Our image-matching algorithm.

    Runs 2 passes: `_find_candidate_matches` to locate potential matches, then
    `_confirm_match` to discard false positives from the first pass.

    Returns an iterator yielding zero or more `(True, position, certainty)`
    tuples for each location where `template` is found within `image`, followed
    by a single `(False, position, certainty)` tuple when there are no further
    matching locations.
    """

    # pylint:disable=undefined-loop-variable
    for i, first_pass_matched, region, first_pass_certainty in \
            _find_candidate_matches(image, template, mask, match_parameters,
                                    imglog):
        confirmed = (
            first_pass_matched and
            _confirm_match(image, region, template, mask, match_parameters,
                           imwrite=lambda name, img: imglog.imwrite(
                               "match%d-%s" % (i, name), img)))  # pylint:disable=cell-var-from-loop

        yield (confirmed, list(region), first_pass_matched,
               first_pass_certainty)
        if not confirmed:
            break


def _find_candidate_matches(image, template, mask, match_parameters, imglog):
    """First pass: Search for `template` in the entire `image`.

    This searches the entire image, so speed is more important than accuracy.
    False positives are ok; we apply a second pass later (`_confirm_match`) to
    weed out false positives.

    http://docs.opencv.org/modules/imgproc/doc/object_detection.html
    http://opencv-code.com/tutorials/fast-template-matching-with-image-pyramid
    """

    imglog.imwrite("source", image)
    imglog.imwrite("template", template)
    imglog.imwrite("mask", mask)
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
    template_pyramid = _build_pyramid(template, levels)
    mask_pyramid = _build_pyramid(mask, len(template_pyramid), is_mask=True)
    image_pyramid = _build_pyramid(image, len(template_pyramid))
    roi_mask = None  # Initial region of interest: The whole image.

    for level in reversed(range(len(template_pyramid))):
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
            relax = 0.01
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
        rois = [  # Initial region of interest: The whole image.
            _Rect(0, 0, matches_heatmap.shape[1], matches_heatmap.shape[0])]
    else:
        rois = [_Rect(*x) for x in cv2_compat.find_contour_boxes(
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

    if mask is not None:
        kwargs = {"mask": mask}
    else:
        kwargs = {}  # For OpenCV < 3.0.0
    for roi in rois:
        r = roi.expand(_Size(*template.shape[:2])).shrink(_Size(1, 1))
        ddebug("Level %d: Searching in %s" % (level, roi))
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
        # normalisation based solely on the template image.
        #
        # We still get a number between 0 - 1, but we normalise such that
        # if the frame is (randomly) decorrelated with the template we will on
        # average get a certainty of 0.

        if mask is not None:
            t16 = template[mask == 255].astype(numpy.uint16)
        else:
            t16 = template.astype(numpy.uint16)

        # This is the average sqdiff we would get comparing this template
        # against all possible frames.  So feed in random noise as `frame` and
        # you'll get a number close to this value.  This allows us to normalise
        # random noise to certainty=0.
        scale = float(numpy.sum(t16 ** 2 - 255 * t16 + 255 ** 2 / 3))

        if mask is not None:
            # matchTemplateMask normalises the source & template image to [0,1].
            # https://github.com/opencv/opencv/blob/3.2.0/modules/imgproc/src/templmatch.cpp#L840-L917
            scale /= (255 ** 2)
        scale = max(scale, 1)
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


def _build_pyramid(image, levels, is_mask=False):
    """A "pyramid" is [an image, the same image at 1/2 the size, at 1/4, ...]

    As a performance optimisation, image processing algorithms work on a
    "pyramid" by first identifying regions of interest (ROIs) in the smallest
    image; if results are positive, they proceed to the next larger image, etc.
    See http://docs.opencv.org/doc/tutorials/imgproc/pyramids/pyramids.html

    The original-sized image is called "level 0", the next smaller image "level
    1", and so on. This numbering corresponds to the array index of the
    "pyramid" array.
    """
    if image is None:
        return [None] * levels
    pyramid = [image]
    for _ in range(levels - 1):
        if any(x < 20 for x in pyramid[-1].shape[:2]):
            break
        downsampled = cv2.pyrDown(pyramid[-1])
        if is_mask:
            cv2.threshold(downsampled, 254, 255, cv2.THRESH_BINARY, downsampled)
        pyramid.append(downsampled)
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


def _confirm_match(image, region, template, mask, match_parameters, imwrite):
    """Second pass: Confirm that `template` matches `image` at `region`.

    This only checks `template` at a single position within `image`, so we can
    afford to do more computationally-intensive checks than
    `_find_candidate_matches`.
    """

    if match_parameters.confirm_method == ConfirmMethod.NONE:
        return True

    # Set Region Of Interest to the "best match" location
    image = image[region.y:region.bottom, region.x:region.right]
    imwrite("confirm-source_roi", image)
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    imwrite("confirm-source_roi_gray", image)
    imwrite("confirm-template_gray", template)

    if mask is not None:
        mask = mask[:, :, 0]

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

    title = "stbt.match(%r): %s" % (
        imglog.data["template_name"],
        "Matched" if any(imglog.data["matches"]) else "Didn't match")

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
        <h4>{{title}}</h4>

        <img src="source_with_matches.png" />

        <h5>First pass (find candidate matches):</h5>

        <p>Searching for <b>template</b> {{link("template")}}
            {% if "mask" in images %}
            with <b>transparency mask</b> {{link("mask")}}
            {% endif %}
            within <b>source</b> image {{link("source")}}

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
        ConfirmMethod=ConfirmMethod,
        link=link,
        MatchMethod=MatchMethod,
        show_second_pass=any(
            x._first_pass_matched for x in imglog.data["matches"]),  # pylint:disable=protected-access
        title=title,
    )
