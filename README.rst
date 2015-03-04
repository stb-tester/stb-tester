======
 stbt
======

--------------------------------------------------------------
Automated User Interface Testing for Set-Top Boxes & Smart TVs
--------------------------------------------------------------

.. image:: https://travis-ci.org/stb-tester/stb-tester.png?branch=master
   :target: https://travis-ci.org/stb-tester/stb-tester

:Copyright: Copyright (C) 2013-2014 Stb-tester.com Ltd,
            2012-2014 YouView TV Ltd. and other contributors
:License: LGPL v2.1 or (at your option) any later version (see LICENSE file in
          the source distribution for details)
:Version: @VERSION@
:Manual section: 1
:Manual group: stb-tester

SYNOPSIS
========

stbt record [options]

stbt run [options] script[::testcase]


DESCRIPTION
===========

**stbt record** will record a test case by listening for remote-control
keypresses, taking screenshots from the set-top box as it goes.

You then (manually) crop the screenshots to the region of interest.

(Optionally) you manually edit the generated test script, which will look
something like this::

    def test_that_i_can_tune_to_bbc_one_from_the_guide():
        press("MENU")
        wait_for_match("Guide.png")
        press("OK")
        wait_for_match("BBC One.png")

**stbt run** will play back the given test script, returning an exit status of
success or failure for easy integration with your existing test reporting
system.

**stbt** has other auxiliary sub-commands; run `stbt --help` for details.


OPTIONS
=======

Global options
--------------

--control=<uri>
  A remote control to use for controlling the set top box. `uri` can be:

  lirc:([<lircd_socket>]|[<hostname>:]<port>):<remote_control_name>
    A hardware infrared emitter controlled by the lirc (Linux Infrared Remote
    Control) daemon.

    * If `lircd_socket` is specified (or none of `lircd_socket`, `hostname` and
      `port` are specified) remote control commands are sent via a lircd socket
      file. `lircd_socket` defaults to `/var/run/lirc/lircd`.
    * If `port` is specified, remote control commands are sent via a lircd TCP
      listener on localhost.
    * If `hostname` and `port` are specified, remote control commands are sent
      via a lircd TCP listener on a remote host.

    `remote_control_name` is the name of a remote-control specification in
    lircd.conf.

    Examples:
        | lirc::myremote
        | lirc:/var/run/lirc/lircd:myremote
        | lirc:8700:myremote
        | lirc:192.168.100.100:8700:myremote

  irnetbox:<hostname>[:<port>]:<output>:<config_file>
    RedRat irNetBox network-controlled infrared emitter hardware.
    `hostname` is the hostname or IP address of the irNetBox device.
    `port` is the TCP port of the irNetBox device. It defaults to 10001, which
    is the port used by real irNetBox devices; override if using an irNetBox
    proxy that listens on a different port.
    `output` is the infrared output to use, a number between 1 and 16
    (inclusive). `config_file` is the configuration file that describes the
    infrared protocol to use; it can be created with RedRat's (Windows-only)
    "IR Signal Database Utility".
    stbt supports the irNetBox models II and III.

  samsung:<hostname>[:<port>]
    Can be used to control Samsung Smart TVs using the same TCP network
    protocol that their mobile phone app uses.  Tested against a Samsung
    UE32F5370 but will probably work with all recent Samsung Smart TVs.

  vr:<hostname>[:<port>]
    A "virtual remote" that communicates with the set-top box over TCP.
    Requires a virtual remote listener (which we haven't released yet) running
    on the set-top box.

  none
    Ignores key press commands.

  test
    Used by the selftests to change the input video stream. Only works with
    `--source-pipeline=videotestsrc`. A script like `press("18")` will change
    videotestsrc's pattern property (see `gst-inspect videotestsrc`).

  x11:<display>
    Send keypresses to a given X display using the xtest extension. Can be used
    with GStreamer's ximagesrc for testing desktop applications and websites.
    The key names are X keysyms, i.e. "a", "b", "comma", "space", etc.  For a
    full list see http://www.cl.cam.ac.uk/~mgk25/ucs/keysyms.txt .

    Requires that `xdotool` is installed.

--source-pipeline=<pipeline>
  A GStreamer pipeline providing a video stream to use as video output from the
  set-top box under test.  For the Hauppauge HD PVR use::

      v4l2src device=/dev/video0 ! tsdemux ! h264parse

--sink-pipeline=<pipeline>
  A GStreamer pipeline to use for video output, like `xvimagesink`.

--restart-source
  Restart the GStreamer source pipeline when video loss is detected, to work
  around the behaviour of the Hauppauge HD PVR video-capture device.

-v, --verbose
  Enable debug output.

  With `stbt run`, specify `-v` twice to dump intermediate images from the
  image processing algorithm to the `./stbt-debug` directory. Note that this
  will dump a *lot* of files -- several images per frame processed. This is
  intended for debugging the image processing algorithm; it isn't intended for
  end users.

Additional options to stbt run
------------------------------

--save-video=<file>
  Record a video (in the HTML5-compatible WebM format) to the specified `file`.

Additional options to stbt record
---------------------------------

--control-recorder=<uri>
  The source of remote control presses.  `uri` can be:

  lirc:([<lircd_socket>]|[<hostname>:]<port>):<remote_control_name>
    A hardware infrared receiver controlled by the lirc (Linux Infrared Remote
    Control) daemon. Parameters are as for `--control`.

  vr:<hostname>:<port>
    Listens on the socket <hostname>:<port> for a connection and reads a
    "virtual remote" stream (which we haven't documented yet, but we'll
    probably change it soon to be compatible with LIRC's protocol).

  file://<filename>
    Reads remote control keypresses from a newline-separated list of key names.
    For example, `file:///dev/stdin` to use the keyboard as the remote control
    input.

  stbt-control[:<keymap_file>]
    Launches **stbt control** to record remote control keypresses using the PC
    keyboard. See `stbt control --help` for details. Disables `--verbose`
    parameter.

-o <filename>, --output-filename=<filename>
  The file to write the generated test script to.


CONFIGURATION
=============

All parameters that can be passed to the stbt tools can also be specified in
configuration files. Configuration is searched for in the following files (with
later files taking precedence):

1. /etc/stbt/stbt.conf
2. ~/.config/stbt/stbt.conf
3. $STBT_CONFIG_FILE

$STBT_CONFIG_FILE is a colon-separated list of files where the item specified
at the beginning takes precedence.

These files are simple ini files with the form::

    [global]
    source_pipeline = videotestsrc
    sink_pipeline = xvimagesink sync=false
    control = None
    verbose = 0
    [run]
    save_video = video.webm
    [record]
    output_file = test.py
    control_recorder = file:///dev/stdin

Each key corresponds to a command line option with hyphens replaced with
underscores.


EXIT STATUS
===========

0 on success; 1 on test script failure; 2 on any other error.

Test scripts indicate **failure** (the system under test didn't behave as
expected) by raising an instance of `stbt.UITestFailure` (or a subclass
thereof) or `AssertionError` (which is raised by Python's `assert` statement).
Any other exception is considered a test **error** (a logic error in the test
script, an error in the system under test's environment, or an error in the
test framework itself).


HARDWARE REQUIREMENTS
=====================

The test rig consists of a Linux server, with:

* A video-capture card (for capturing the output from the system under test)
* An infrared receiver (for recording the system-under-test's infrared
  protocol)
* An infrared emitter (for controlling the system under test)

Video capture card
------------------

You'll need a capture card with drivers supporting the V4L2 API
(Video-for-Linux 2). We recommend a capture card with mature open-source
drivers, preferably drivers already present in recent versions of the Linux
kernel.

The Hauppauge HD PVR works well (and works out of the box on recent versions of
Fedora), though it doesn't support 1080p. If you need an HDCP stripper, try the
HD Fury III.

Infra-red emitter and receiver
------------------------------

An IR emitter+receiver such as the RedRat3, plus a LIRC configuration file
with the key codes for your set-top box's remote control.

Using software components instead
---------------------------------

If you don't mind instrumenting the system under test, you don't even need the
above hardware components.

stb-tester uses GStreamer, an open source multimedia framework. Instead of a
video-capture card you can use any GStreamer video-source element. For example:

* If you run tests against a VM running the set-top box software instead
  of a physical set-top box, you could use the ximagesrc GStreamer
  element to capture video from the VM's X Window.

* If your set-top box uses DirectFB, you could install the DirectFBSource
  GStreamer element (https://bugzilla.gnome.org/show_bug.cgi?id=685877) on the
  set-top box to stream video to a updsrc GStreamer element on the test rig.

Instead of a hardware infra-red receiver + emitter, you can use a software
equivalent (for example a server running on the set-top box that listens on
a TCP socket instead of listening for infra-red signals, and your own
application for emulating remote-control keypresses). Using a software remote
control avoids all issues of IR interference in rigs testing multiple set-top
boxes at once.

Linux server
------------

An 8-core machine will be able to drive 4 set-top boxes simultaneously with at
least 1 frame per second per set-top box.


SOFTWARE REQUIREMENTS
=====================

* A Unixy operating system (we have only tested on Linux and Mac OS X).

* Drivers for any required hardware components.

* GStreamer 1.0 (multimedia framework) + gstreamer-plugins-base +
  gstreamer-plugins-good.

* python 2.7 + pygst + docutils (for building the documentation) + nose (for
  the self-tests).

* OpenCV (image processing library) version >= 2.0.0, and the OpenCV python
  bindings.

* For the Hauppauge video capture device you'll need the gstreamer-libav
  package (e.g. from the rpmfusion-free repository) for H.264 decoding.


INSTALLING FROM SOURCE
======================

Run "make install" from the stb-tester source directory.

See http://stb-tester.com/getting-started.html for the required dependencies
and configuration.


TEST SCRIPT FORMAT
==================

The test scripts produced and run by **stbt record** and **stbt run**,
respectively, are actually python scripts, so you can use the full power of
python. Don't get too carried away, though; aim for simplicity, readability,
and maintainability.

The following functions are available:

.. <start python docs>

as_precondition(message)
    Context manager that replaces test failures with test errors.

    If you run your test scripts with stb-tester's batch runner, the reports it
    generates will show test failures (that is, `stbt.UITestFailure` or
    `AssertionError` exceptions) as red results, and test errors (that is,
    unhandled exceptions of any other type) as yellow results. Note that
    `wait_for_match`, `wait_for_motion`, and similar functions raise a
    `stbt.UITestFailure` when they detect a failure. By running such functions
    inside an `as_precondition` context, any `stbt.UITestFailure` or
    `AssertionError` exceptions they raise will be caught, and a
    `stbt.PreconditionError` will be raised instead.

    When running a single test script hundreds or thousands of times to
    reproduce an intermittent defect, it is helpful to mark unrelated failures
    as test errors (yellow) rather than test failures (red), so that you can
    focus on diagnosing the failures that are most likely to be the particular
    defect you are interested in.

    `message` is a string describing the precondition (it is not the error
    message if the precondition fails).

    For example:

    >>> with as_precondition("Channels tuned"):  #doctest:+NORMALIZE_WHITESPACE
    ...     # Call tune_channels(), which raises:
    ...     raise UITestFailure("Failed to tune channels")
    Traceback (most recent call last):
      ...
    PreconditionError: Didn't meet precondition 'Channels tuned'
    (original exception was: Failed to tune channels)

class ConfigurationError(Exception)
    An error with your stbt configuration file.

debug(msg)
    Print the given string to stderr if stbt run `--verbose` was given.

detect_match(image, timeout_secs=10, noise_threshold=None, match_parameters=None)
    Generator that yields a sequence of one `MatchResult` for each frame
    processed from the source video stream.

    `image` is the image used as the template during matching.  See `stbt.match`
    for more information.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It will be removed in a future release; please use
    `match_parameters.confirm_threshold` intead.

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.

detect_motion(timeout_secs=10, noise_threshold=None, mask=None)
    Generator that yields a sequence of one `MotionResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    `noise_threshold` (float) default: 0.84
      `noise_threshold` is a parameter used by the motiondetect algorithm.
      Increase `noise_threshold` to avoid false negatives, at the risk of
      increasing false positives (a value of 0.0 will never report motion).
      This is particularly useful with noisy analogue video sources.
      The default value is read from `motion.noise_threshold` in your
      configuration file.

    `mask` (str) default: None
      A mask is a black and white image that specifies which part of the image
      to search for motion. White pixels select the area to search; black
      pixels the area to ignore.

draw_text(text, duration_secs=3)
    Write the specified `text` to the video output.

    `duration_secs` is the number of seconds that the text should be displayed.

frames(timeout_secs=None)
    Generator that yields frames captured from the GStreamer pipeline.

    "timeout_secs" is in seconds elapsed, from the method call. Note that
    you can also simply stop iterating over the sequence yielded by this
    method.

    Returns an (image, timestamp) tuple for every frame captured, where
    "image" is in OpenCV format.

get_config(section, key, default=None, type_=<type 'str'>)
    Read the value of `key` from `section` of the stbt config file.

    See 'CONFIGURATION' in the stbt(1) man page for the config file search
    path.

    Raises `ConfigurationError` if the specified `section` or `key` is not
    found, unless `default` is specified (in which case `default` is returned).

get_frame()
    Returns an OpenCV image of the current video frame.

is_screen_black(frame=None, mask=None, threshold=None)
    Check for the presence of a black screen in a video frame.

    `frame` (numpy.array)
      If this is specified it is used as the video frame to check; otherwise a
      frame is grabbed from the source video stream. It is a `numpy.array` in
      OpenCV format (for example as returned by `frames` and `get_frame`).

    `mask` (string)
      The filename of a black & white image mask. It must have white pixels for
      parts of the frame to check and black pixels for any parts to ignore.

    `threshold` (int) default: 10
      Even when a video frame appears to be black, the intensity of its pixels
      is not always 0. To differentiate almost-black from non-black pixels, a
      binary threshold is applied to the frame. The `threshold` value is
      in the range 0 (black) to 255 (white). The global default can be changed
      by setting `threshold` in the `[is_screen_black]` section of `stbt.conf`.

match(image, frame=None, match_parameters=None, region=Region.ALL)
    Search for `image` in a single frame of the source video stream.
    Returns a `MatchResult`.

    `image` (string or numpy.array)
      The image used as the template during matching. It can either be the
      filename of a png file on disk or a numpy array containing the pixel data
      in 8-bit BGR format.

      8-bit BGR numpy arrays are the same format that OpenCV uses for images.
      This allows generating templates on the fly (possibly using OpenCV) or
      searching for images captured from the system under test earlier in the
      test script.

    `frame` (numpy.array) default: None
      If this is specified it is used as the video frame to search in;
      otherwise a frame is grabbed from the source video stream. It is a
      `numpy.array` in OpenCV format (for example as returned by `frames` and
      `get_frame`).

    `match_parameters` (stbt.MatchParameters) default: MatchParameters()
      Customise the image matching algorithm. See the documentation for
      `MatchParameters` for details.

    `region` (stbt.Region) default: Region.ALL
      Only search within the specified region of the video frame.

match_text(text, frame=None, region=Region.ALL, mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD, lang=None, tesseract_config=None)
    Search the screen for the given text.

    Can be used as an alternative to `match`, etc. searching for text
    instead of an image.

    Args:
        text (unicode): Text to search for.

    Kwargs:
        Refer to the arguments to `ocr()`.

    Returns:
        TextMatchResult.  Will evaluate to True if text matched, false
        otherwise.

    Example:

    Select a button in a vertical menu by name.  In this case "TV Guide".

    ::

        m = stbt.match_text(u"TV Guide", match('button-background.png').region)
        assert m.match
        while not stbt.match('selected-button.png').region.contains(m.region):
            press('KEY_DOWN')

class MatchParameters
    Parameters to customise the image processing algorithm used by
    `match`, `wait_for_match`, `detect_match`, and `press_until_match`.

    You can change the default values for these parameters by setting
    a key (with the same name as the corresponding python parameter)
    in the `[match]` section of your stbt.conf configuration file.

    `match_method` (str) default: sqdiff-normed
      The method that is used by the OpenCV `cvMatchTemplate` algorithm to find
      likely locations of the "template" image within the larger source image.

      Allowed values are ``"sqdiff-normed"``, ``"ccorr-normed"``, and
      ``"ccoeff-normed"``. For the meaning of these parameters, see the OpenCV
      `cvMatchTemplate` reference documentation and tutorial:

      * http://docs.opencv.org/modules/imgproc/doc/object_detection.html
      * http://docs.opencv.org/doc/tutorials/imgproc/histograms/
                                       template_matching/template_matching.html

    `match_threshold` (float) default: 0.80
      How strong a result from `cvMatchTemplate` must be, to be considered a
      match. A value of 0 will mean that anything is considered to match,
      whilst a value of 1 means that the match has to be pixel perfect. (In
      practice, a value of 1 is useless because of the way `cvMatchTemplate`
      works, and due to limitations in the storage of floating point numbers in
      binary.)

    `confirm_method` (str) default: absdiff
      The result of the previous `cvMatchTemplate` algorithm often gives false
      positives (it reports a "match" for an image that shouldn't match).
      `confirm_method` specifies an algorithm to be run just on the region of
      the source image that `cvMatchTemplate` identified as a match, to confirm
      or deny the match.

      The allowed values are:

      "``none``"
          Do not confirm the match. Assume that the potential match found is
          correct.

      "``absdiff``" (absolute difference)
          The absolute difference between template and source Region of
          Interest (ROI) is calculated; thresholded and eroded to account for
          potential noise; and if any white pixels remain then the match is
          deemed false.

      "``normed-absdiff``" (normalized absolute difference)
          As with ``absdiff`` but both template and ROI are normalized before
          the absolute difference is calculated. This has the effect of
          exaggerating small differences between images with similar, small
          ranges of pixel brightnesses (luminance).

          This method is more accurate than ``absdiff`` at reporting true and
          false matches when there is noise involved, particularly aliased
          text. However it will, in general, require a greater
          confirm_threshold than the equivalent match with absdiff.

          When matching solid regions of colour, particularly where there are
          regions of either black or white, ``absdiff`` is better than
          ``normed-absdiff`` because it does not alter the luminance range,
          which can lead to false matches. For example, an image which is half
          white and half grey, once normalised, will match a similar image
          which is half white and half black because the grey becomes
          normalised to black so that the maximum luminance range of [0..255]
          is occupied. However, if the images are dissimilar enough in
          luminance, they will have failed to match the `cvMatchTemplate`
          algorithm and won't have reached the "confirm" stage.

    `confirm_threshold` (float) default: 0.16
      Increase this value to avoid false negatives, at the risk of increasing
      false positives (a value of 1.0 will report a match every time).

    `erode_passes` (int) default: 1
      The number of erode steps in the `absdiff` and `normed-absdiff` confirm
      algorithms. Increasing the number of erode steps makes your test less
      sensitive to noise and small variances, at the cost of being more likely
      to report a false positive.

    Please let us know if you are having trouble with image matches so that we
    can further improve the matching algorithm.

class MatchResult
    * `timestamp`: Video stream timestamp.
    * `match`: Boolean result, the same as evaluating `MatchResult` as a bool.
      e.g: `if match_result:` will behave the same as `if match_result.match`.
    * `region`: The `Region` in the video frame where the image was found.
    * `first_pass_result`: Value between 0 (poor) and 1.0 (excellent match)
      from the first pass of the two-pass templatematch algorithm.
    * `frame`: The video frame that was searched, in OpenCV format.
    * `image`: The template image that was searched for, as given to `match`.
    * `position`: `Position` of the match, the same as in `region`. Included
      for backwards compatibility; we recommend using `region` instead.

class MatchTimeout(UITestFailure)
    * `screenshot`: An OpenCV image from the source video when the search
      for the expected image timed out.
    * `expected`: Filename of the image that was being searched for.
    * `timeout_secs`: Number of seconds that the image was searched for.

class MotionResult
    * `timestamp`: Video stream timestamp.
    * `motion`: Boolean result.

class MotionTimeout(UITestFailure)
    * `screenshot`: An OpenCV image from the source video when the search
      for motion timed out.
    * `mask`: Filename of the mask that was used (see `wait_for_motion`).
    * `timeout_secs`: Number of seconds that motion was searched for.

class NoVideo(UITestFailure)
    No video available from the source pipeline.

ocr(frame=None, region=Region.ALL, mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD, lang=None, tesseract_config=None, tesseract_user_words=None, tesseract_user_patterns=None)
    Return the text present in the video frame as a Unicode string.

    Perform OCR (Optical Character Recognition) using the "Tesseract"
    open-source OCR engine, which must be installed on your system.

    If `frame` isn't specified, take a frame from the source video stream.
    If `region` is specified, only process that region of the frame; otherwise
    process the entire frame.

    `lang` is the three letter ISO-639-3 language code of the language you are
    attempting to read.  e.g. "eng" for English or "deu" for German.  More than
    one language can be specified if joined with '+'.  e.g. lang="eng+deu" means
    that the text to be read may be in a mixture of English and German.  To read
    a language you must have the corresponding tesseract language pack
    installed.  This language code is passed directly down to the tesseract OCR
    engine.  For more information see the tesseract documentation.  `lang`
    defaults to English.

    `tesseract_config` (dict)
      Allows passing configuration down to the underlying OCR engine.  See the
      tesseract documentation for details:
      https://code.google.com/p/tesseract-ocr/wiki/ControlParams

    `tesseract_user_words` (list of unicode strings)
      List of words to be added to the tesseract dictionary.  Can help matching.
      To replace the tesseract system dictionary set
      `tesseract_config['load_system_dawg'] = False` and
      `tesseract_config['load_freq_dawg'] = False`.

    `tesseract_user_patterns` (list of unicode strings)
      List of patterns to be considered as if they had been added to the
      tesseract dictionary.  Can aid matching.  See the tesseract documentation
      for information on the format of the patterns:
      http://tesseract-ocr.googlecode.com/svn/trunk/doc/tesseract.1.html#_config_files_and_augmenting_with_user_data

class OcrMode
    Options to control layout analysis and assume a certain form of image.

    For a (brief) description of each option, see the tesseract(1) man page:
    http://tesseract-ocr.googlecode.com/svn/trunk/doc/tesseract.1.html

    ORIENTATION_AND_SCRIPT_DETECTION_ONLY = 0
    PAGE_SEGMENTATION_WITHOUT_OSD = 3
    PAGE_SEGMENTATION_WITHOUT_OSD_OR_OCR = 2
    PAGE_SEGMENTATION_WITH_OSD = 1
    SINGLE_CHARACTER = 10
    SINGLE_COLUMN_OF_TEXT_OF_VARIABLE_SIZES = 4
    SINGLE_LINE = 7
    SINGLE_UNIFORM_BLOCK_OF_TEXT = 6
    SINGLE_UNIFORM_BLOCK_OF_VERTICALLY_ALIGNED_TEXT = 5
    SINGLE_WORD = 8
    SINGLE_WORD_IN_A_CIRCLE = 9

class Position
    A point within the video frame.

    `x` and `y` are integer coordinates (measured in number of pixels) from the
    top left corner of the video frame.

class PreconditionError(UITestError)
    Exception raised by `as_precondition`.

press(key, interpress_delay_secs=None)
    Send the specified key-press to the system under test.

    The mechanism used to send the key-press depends on what you've configured
    with `--control`.

    `key` is a string. The allowed values depend on the control you're using:
    If that's lirc, then `key` is a key name from your lirc config file.

    `interpress_delay_secs` (float) default: 0
      Specifies a minimum time to wait after the preceding key press, in order
      to accommodate the responsiveness of the device under test.

      The global default for `interpress_delay_secs` can be set in the
      configuration file, in section `press`.

press_until_match(key, image, interval_secs=None, noise_threshold=None, max_presses=None, match_parameters=None)
    Calls `press` as many times as necessary to find the specified `image`.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `max_presses` times.

    `interval_secs` (int) default: 3
      The number of seconds to wait for a match before pressing again.

    `max_presses` (int) default: 10
      The number of times to try pressing the key and looking for the image
      before giving up and throwing `MatchTimeout`

    `noise_threshold` (string) DEPRECATED
      `noise_threshold` is marked for deprecation but appears in the args for
      backward compatibility with positional argument syntax. It will be
      removed in a future release; please use
      `match_parameters.confirm_threshold` instead.

    `match_parameters` (MatchParameters) default: MatchParameters()
      Customise the image matching algorithm. See the documentation for
      `MatchParameters` for details.

class Region
    Rectangular region within the video frame.

    `x` and `y` are the coordinates of the top left corner of the region,
    measured in pixels from the top left of the video frame. The `width` and
    `height` of the rectangle are also measured in pixels.

    Example:

    regions a, b and c::

        - 01234567890123
        0 ░░░░░░░░
        1 ░a░░░░░░
        2 ░░░░░░░░
        3 ░░░░░░░░
        4 ░░░░▓▓▓▓░░▓c▓
        5 ░░░░▓▓▓▓░░▓▓▓
        6 ░░░░▓▓▓▓░░░░░
        7 ░░░░▓▓▓▓░░░░░
        8     ░░░░░░b░░
        9     ░░░░░░░░░

        >>> a = Region(0, 0, 8, 8)
        >>> b = Region.from_extents(4, 4, 13, 10)
        >>> print b
        Region(x=4, y=4, width=9, height=6)
        >>> c = Region(10, 4, 3, 2)
        >>> a.right
        8
        >>> b.bottom
        10
        >>> b.contains(c)
        True
        >>> a.contains(b)
        False
        >>> c.contains(b)
        False
        >>> b.extend(x=6, bottom=-4) == c
        True
        >>> a.extend(right=5).contains(c)
        True
        >>> a.extend(x=3).width
        5
        >>> a.extend(right=-3).width
        5
        >>> print Region.intersect(a, b)
        Region(x=4, y=4, width=4, height=4)
        >>> Region.intersect(c, b) == c
        True
        >>> print Region.intersect(a, c)
        None
        >>> print Region.intersect(None, a)
        None
        >>> quadrant2 = Region(x=float("-inf"), y=float("-inf"),
        ...                    right=0, bottom=0)
        >>> quadrant2.translate(2, 2)
        Region(x=-inf, y=-inf, right=2, bottom=2)
        >>> Region.intersect(Region.ALL, c) == c
        True
        >>> Region.ALL
        Region.ALL
        >>> print Region.ALL
        Region.ALL
        >>> print c.translate(x=-9, y=-3)
        Region(x=1, y=1, width=3, height=2)

save_frame(image, filename)
    Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.

class TextMatchResult
    Return type of `match_text`.

    timestamp: Timestamp of the frame matched against
    match (bool): Whether the text was found or not
    region (Region): The bounding box of the text found or None if no text found
    frame: The video frame matched against
    text (unicode): The text searched for

class UITestError(Exception)
    The test script had an unrecoverable error.

class UITestFailure(Exception)
    The test failed because the system under test didn't behave as expected.

wait_for_match(image, timeout_secs=10, consecutive_matches=1, noise_threshold=None, match_parameters=None)
    Search for `image` in the source video stream.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `timeout_secs` seconds.

    `image` is the image used as the template during matching.  See `match`
    for more information.

    `consecutive_matches` forces this function to wait for several consecutive
    frames with a match found at the same x,y position. Increase
    `consecutive_matches` to avoid false positives due to noise.

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It will be removed in a future release; please use
    `match_parameters.confirm_threshold` instead.

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.

wait_for_motion(timeout_secs=10, consecutive_frames=None, noise_threshold=None, mask=None)
    Search for motion in the source video stream.

    Returns `MotionResult` when motion is detected.
    Raises `MotionTimeout` if no motion is detected after `timeout_secs`
    seconds.

    `consecutive_frames` (str) default: 10/20
      Considers the video stream to have motion if there were differences
      between the specified number of `consecutive_frames`, which can be:

      * a positive integer value, or
      * a string in the form "x/y", where `x` is the number of frames with
        motion detected out of a sliding window of `y` frames.

      The default value is read from `motion.consecutive_frames` in your
      configuration file.

    `noise_threshold` (float) default: 0.84
      Increase `noise_threshold` to avoid false negatives, at the risk of
      increasing false positives (a value of 0.0 will never report motion).
      This is particularly useful with noisy analogue video sources.
      The default value is read from `motion.noise_threshold` in your
      configuration file.

    `mask` (str) default: None
      A mask is a black and white image that specifies which part of the image
      to search for motion. White pixels select the area to search; black
      pixels the area to ignore.

wait_until(callable_, timeout_secs=10, interval_secs=0)
    Wait until a condition becomes true, or until a timeout.

    `callable_` is any python callable, such as a function or a lambda
    expression. It will be called repeatedly (with a delay of `interval_secs`
    seconds between successive calls) until it succeeds (that is, it returns a
    truthy value) or until `timeout_secs` seconds have passed. In both cases,
    `wait_until` returns the value that `callable_` returns.

    After you send a remote-control signal to the system-under-test it usually
    takes a few frames to react, so a test script like this would probably
    fail:

        stbt.press("guide")
        assert match("guide.png")

    Instead, use this:

        stbt.press("guide")
        assert wait_until(lambda: match("guide.png"))

    Note that instead of the above `assert wait_until(...)` you could use
    `wait_for_match("guide.png")`. `wait_until` is a generic solution that
    also works with stbt's other functions, like `match_text` and
    `is_screen_black`.

    `wait_until` also allows composing more complex conditions, such as::

        # Wait until something disappears
        assert wait_until(lambda: not match("xyz.png"))

        # Assert that something doesn't appear within 10 seconds
        assert not wait_until(lambda: match("xyz.png"))

        # Assert that two images are present at the same time:
        assert wait_until(lambda: match("a.png") and match("b.png"))

        # Wait but don't raise an exception:
        if not wait_until(lambda: match("xyz.png")):
            do_something_else()

    There are some drawbacks to using `assert` instead of `wait_for_match`:

    * The exception message won't contain the reason why the match failed
      (unless you specify it as a second parameter to `assert`, which is
      tedious and we don't expect you to do it), and
    * The exception won't have the offending video-frame attached (so the
      screenshot that `stbt batch run` saves alongside the failing test logs
      will be a few frames later than the frame that actually caused the test
      to fail).

    We hope to solve both of the above drawbacks at some point in the future.


.. <end python docs>


TEST SCRIPT BEST PRACTICES
==========================

* When cropping images to be matched by a test case, you must select a region
  that will *not* be present when the test case fails, and that does *not*
  contain *any* elements that might be absent when the test case succeeds. For
  example, you must not include any part of a live TV stream (which will be
  different each time the test case is run), nor translucent menu overlays with
  live TV showing through.

* Crop template images as tightly as possible. For example if you're looking
  for a button, don't include the background outside of the button. (This is
  particularly important if your system-under-test is still under development
  and minor aesthetic changes to the UI are common.)

* Always follow a `press` with a `wait_for_match` -- don't assume that
  the `press` worked.

* Use `press_until_match` instead of assuming that the position of a menu item
  will never change within that menu.

* Use the `timeout_secs` parameter of `wait_for_match` and `wait_for_motion`
  instead of using `time.sleep`.

* Rename the template images captured by `stbt record` to a name that explains
  the contents of the image.

* Extract common navigation patterns into separate python functions. It is
  useful to start each test script by calling a function that brings the
  system-under-test to a known state.


SEE ALSO
========

* http://stb-tester.com/
* http://github.com/stb-tester/stb-tester


AUTHORS
=======

* Will Manley <will@williammanley.net>
* David Rothlisberger <david@rothlis.net>
* Hubert Lacote <hubert.lacote@gmail.com>
* and contributors
