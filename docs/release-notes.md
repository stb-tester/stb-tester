Stb-tester release notes
========================

[Stb-tester] Python APIs for use in test scripts are stable: Upgrading to a
newer stb-tester version shouldn't affect any of your test scripts.
Occasionally we might break some rare edge cases, but we don't expect them to
affect most users, and we mention such changes under "Breaking changes" in the
release notes.

Similarly, the command-line interfaces of *stbt run*, *stbt auto-selftest*,
*stbt batch*, *stbt config*, *stbt control*, *stbt match*, *stbt power*, *stbt
record*, *stbt screenshot*, *stbt tv*, and *stbt virtual-stb* are stable. Other
command-line utilities are considered experimental.

For installation instructions see [Getting Started] if you're using the
open-source project, or update [test_pack.stbt_version] if you're using the
[Stb-tester hardware].

[Stb-tester]: https://stb-tester.com
[Getting Started]: https://github.com/stb-tester/stb-tester/wiki/Getting-started-with-stb-tester
[test_pack.stbt_version]: https://stb-tester.com/manual/advanced-configuration#stbt-conf
[Stb-tester hardware]: https://stb-tester.com/solutions

#### v30

TODO: Date

##### Breaking changes since v29

* Compatibility flag `global.use_old_threading_behaviour` has been removed.
  This was introduced in v28, but seems to be unused. See release notes for v28
  below for more information.

##### New features

##### Bug fixes & improvements

#### v29

New APIs for measuring animations and transitions, and for sending infrared
repeat signals (pressing and holding a button). Plus a bunch of usability
improvements and bug fixes.

19 June 2018.

##### Breaking changes since v28

* `stbt.frames()` returns an iterator of `stbt.Frame` objects, instead of an
  iterator of tuples `(stbt.Frame, int)`. The second field of the tuple was a
  timestamp in nanoseconds; this has been deprecated since we added
  `stbt.Frame.time` in v26, 2 years ago. If you were calling it like this:

        for frame, _ in stbt.frames():

  then you should change it to this:

        for frame in stbt.frames():

* Similarly, removed the deprecated `timestamp` attribute (nanoseconds) from
  `stbt.MatchResult`, `stbt.TextMatchResult`, and `stbt.MotionResult`. Use the
  `time` attribute instead (seconds).

* `stbt.is_screen_black` returns an object with `black` and `frame` attributes,
  instead of a bool. This evaluates to truthy or falsey so this change is
  backwards compatible, unless you were explicitly comparing the result with
  `== True` or `is True`. This change was made so that you can get the exact
  frame that changed to (or from) black, for more precise performance
  measurements.

* The `stbt.NoVideo` exception inherits from `Exception` instead of
  `stbt.UITestFailure`. This means that it will be considered a test *error*,
  not a *failure*. `NoVideo` is usually a fault with your video-capture
  pipeline or hardware, not the device-under-test; most video-capture hardware
  continues to deliver video frames (typically black) even without a video
  source.

* `stbt run` will no longer show an output video window by default. This is a
  better default for headless environments like stbt-docker.  You can re-enable
  this by setting `global.sink_pipeline = xvimagesink sync=false` in your
  stbt.conf file.

* Remove tracing infrastructure (which would report the current test & line
  number to a file specified via the `--save-trace` argument or to a socket
  specified via the `STBT_TRACING_SOCKET` environment variable). This was a
  proof of concept at best, and as far as we know it isn't used by anyone.

##### New features

* Added `stbt.press_and_wait`: Detection and frame-accurate measurement of
  animations and transitions.

* `stbt.press` accepts a new `hold_secs` parameter to hold a key down for the
  specified duration. This is implemented for the LIRC, CEC, and Roku controls.

* Added `stbt.pressing`: A context manager that will hold a key down for as
  long as the code in the `with` block is executing.

* `stbt.press` can be configured to use the ADB keypress mechanism from
  `stbt.android.AdbDevice.press`. See the documentation for `--control` in the
  [stbt(1) man page].

* `stbt.android.AdbDevice.press` will convert some standard Stb-tester key
  names like "KEY_OK" to the equivalent Android KeyEvent keycodes.

* `stbt.wait_for_motion`, `stbt.wait_for_match`, `stbt.detect_motion` and
  `stbt.detect_match` all now take a new optional `frames` parameter. This
  defaults to `stbt.frames()` which preserves the existing behaviour.

* `stbt.ocr` and `stbt.match_text`: Added `text_color_threshold` parameter, to
  configure the threshold used with the `text_color` parameter.

##### Bug fixes & improvements

* If your test-pack is a Python package (that is, it contains an `__init__.py`
  file in each directory under `tests/`) then relative imports from your test
  scripts will now work. This allows you to organise your tests into multiple
  directories easily.

* Fix `AttributeError` when using a `stbt.FrameObject` instance from multiple
  threads.

* `stbt.press`: Fix timing of the key-press visualisation in the recorded
  video. The key-press was appearing a few frames earlier than it was actually
  sent.

* `stbt.Frame`: Show timestamp & dimensions in repr output, instead of the
  verbose numpy repr.

* Internal improvements & simplifications to the GStreamer pipeline.

* Debug logging: `stbt.is_screen_black` logs the result of its analysis,
  similar to `stbt.match`, `stbt.ocr`, etc.

* Debug logging: Only log 3 decimal places for frame timestamps. 60fps is 16ms
  per frame, so higher precision is misleading.

* `stbt auto-selftest` bug-fixes: Don't fail if there are Python files in the
  root of the test-pack; don't abort if one of the files specified explicitly
  doesn't have any selftests; when specifying files explicitly, remove the
  generated file if the source file no longer has any selftests.

* `stbt batch run` will write the final screenshot to the results directory
  even if the test-script changed the current working directory with `os.chdir`.

#### v28

Better defaults; multithreading support; Android & VNC control mechanisms;
many API improvements and bugfixes.

24 January 2018.

##### Breaking changes since v27

* The default parameters for the image-matching algorithm have changed from
  `MatchParameters(confirm_method="absdiff", confirm_threshold=0.16)` to
  `MatchParameters(confirm_method="normed-absdiff" confirm_threshold=0.30)`.
  This has been our recommended setting for several years; now it's the
  default. The "normed-absdiff" algorithm works better in most cases, except
  when you're looking for an image with very little structure (for example a
  plain patch of a single colour). We recommend that you always include some
  structure (edges) in your reference images; if you really need to match a
  plain blob of colour, you can override the algorithm for specific invocations
  of `stbt.match` by passing a `match_parameters` argument.

  To keep using the previous defaults, add this to the `[match]` section of
  your stbt config file:

      confirm_method=absdiff
      confirm_threshold=0.16

  Note that users of the [Stb-tester hardware] have always been been using
  these new values, as we provide a custom stbt.conf file to our customers.

* The default `interpress_delay_secs` for `stbt.press` is now 0.3 instead of 0.
  This matches best practices and what the documentation actually says. To keep
  using the previous default, add this to the `[press]` section of your stbt
  config file:

      interpress_delay_secs = 0

  Thanks to Rinaldo Merlo for the bug report.

  Note that users of the [Stb-tester hardware] have always been using the
  best-practices default value of 0.3, as we provide a custom stbt.conf file to
  our customers.

* Passing `region=None` to `stbt.ocr` raises a TypeError. Use
  `region=stbt.Region.ALL` instead. Note that passing `None` has printed a
  deprecation warning since v0.21 (three years ago); raising an exception will
  force users to update their test scripts, allowing us to change the behaviour
  again in a future release to be consistent with `stbt.match_text` where
  `None` means an empty region.

* Passing `type_=bool` to `stbt.get_config` now returns False for values of
  "0", "false", "off", and "no" (all of these are checked in a case-insensitive
  manner). Previously it would always return True for any non-empty value.

* Removed workaround for 4 year old deadlock bug in decklinksrc. If this is
  still necessary, set `source_teardown_eos = True` in the `[global]` section
  of your stbt config file, and let us know on the mailing list as we may
  remove the workaround completely in a future release.

* A call to `stbt.get_frame()` is no-longer guaranteed to return a new frame, it
  may return the same frame that the previous call to `stbt.get_frame()`
  returned. This may have subtle effects on the timing of existing test-scripts.
  Functions that depend on this behaviour should be refactored to use the
  `stbt.frames()` iterator method instead.

  If this change causes you problems you can add:

      [global]
      use_old_threading_behaviour = true

  to your `stbt.conf` to restore the old behaviour. This option may be removed
  in the future. Please let us know on [stb-tester/stb-tester#449] if this will
  cause you problems.

  The benefit is that you can now call `stbt.get_frame()` from multiple threads
  and usage like `wait_until(lambda: match('a.png') or match('b.png'))` will run
  faster as the second `match` will no longer block waiting for a new frame.

* `stbt.get_frame()` and `stbt.frames()` now return read-only frames for better
  performance.  Use `frame.copy()` to get a writeable copy of the frame.

[stb-tester/stb-tester#449]: https://github.com/stb-tester/stb-tester/pull/449

##### New features

* Python API: stbt can now be used from multiple threads simultaneously. Each
  call to `stbt.frames()` returns an independent iterator that can be used
  concurrently.  Example, wait for tv to start playing or an error screen:

      pool = multiprocessing.pool.ThreadPool()
      result = pool.imap_unordered(apply, [
            lambda: wait_for_motion(),
            lambda: wait_for_match("error-screen.png")
        ]).next()
      if isinstance(result, MotionResult):
          print "TV is playing ok"
      else:
          print "Error screen"

* New Android control mechanism to send taps, swipes, and key events. See the
  `stbt.android.AdbDevice` docstrings for usage instructions. You can capture
  video from an Android mobile device using HDMI video-capture via an "MHL"
  USB-to-HDMI cable, or with the
  [Stb-tester CAMERA](https://stb-tester.com/stb-tester-camera) pointed at the
  device's screen, or even by taking screenshots via `AdbDevice.get_frame` (but
  if you're using `AdbDevice.get_frame` the Android device wont be visible in
  the output video as this mechanism bypasses stb-tester's GStreamer pipeline).
  See
  <https://stb-tester.com/blog/2017/02/21/testing-video-playback-on-mobile-devices>
  for a discussion of the trade-offs of each video-capture mechanism.

* New control mechanism using the VNC RFB protocol. This protocol is used by
  Cisco to control some of their set-top boxes. Thanks to Antonio Fin and
  Fabrice Triboix, both at Cisco.

* Python API: New function `stbt.crop` to crop a region from a video-frame.

* Python API: New function `stbt.load_image` to load an image from disk, using
  the same path lookup algorithm that `stbt.match` uses.

* Python API: The `mask` parameter to `stbt.detect_motion`,
  `stbt.wait_for_motion`, and `stbt.is_screen_black` can be an OpenCV image
  (previously it could only be a filename). This makes it easier to construct
  masks programmatically.

* Python API: `stbt.detect_motion`, `stbt.wait_for_motion`, and
  `stbt.is_screen_black` can take a new `region` parameter.

* Python API: `stbt.wait_until` has two new parameters: `predicate` and
  `stable_secs`. Together they allow waiting for something to stabilise (for
  example to wait for the position of a moving selection to stop moving).

* Python API: `stbt.ocr` and `stbt.match_text` have a new parameter
  `text_color`. Specifying this can improve OCR results when tesseract's
  default thresholding algorithm doesn't detect the text, for example for
  light-colored text or text on a translucent overlay.

* Python API: The pre-processing performed by `stbt.ocr` and `stbt.match_text`
  can now be disabled by passing `upscale=False`. This is useful if you want
  to do your own pre-processing.

* Python API: The default `lang` (language) parameter to `stbt.ocr` and
  `stbt.match_text` is now configurable. Set `lang` in the `[ocr]` section
  of your configuration file.

* Python API: Added `region` parameter to `stbt.press_until_match`. Thanks
  to Rinaldo Merlo for the patch.

* OpenCV 3 compatibility: stb-tester will now work with either OpenCV 2.4 or
  OpenCV 3. This support is in beta, please let us know if you see anything not
  working properly with OpenCV 3. OpenCV 2.4 is still our primary supported
  target version of OpenCV.

* Output video now runs a the full frame-rate of the input video rather than
  slowing down during `wait_for_match`. As a side-effect the latency of the
  video has increased by 0.5s and if the image processing is particularly slow
  the annotations won't appear on the output video. Apart from that caveat,
  annotations now appear if you got the frame using `stbt.get_frame()`
  (previously the annotations only appeared if the frames came from a
  `stbt.frames()` iterator). "Annotations" means the yellow & red rectangles
  showing the current match, etc.

##### Minor fixes and packaging fixes

* The `irnetbox` control now understands "double signals" in the irNetBox
  config file generated by the RedRat IR Signal Database Utility. Thanks to
  Rinaldo Merlo for the fix.

* Fixed `stbt power` for ATEN power supplies with more than 8 ports. Thanks to
  Lucas Maneos at YouView for the patch.

* `stbt batch run`: New option `--no-save-video` disables video recordings of
  each test-run. This can be used to reduce CPU consumption when video
  recordings aren't required or are being captured in some other way.

* `stbt lint`: Catch & ignore pylint inference exceptions.

* `stbt auto-selftest`: Fix when running for the first time (when the
  auto_selftest directory doesn't exist).

* Python API: The `is_visible` property of `stbt.FrameObject` subclasses can
  call other public properties. Furthermore, the value of `is_visible` is
  always a bool, so you don't have to remember to cast it to bool in your
  implementation.

* Python API: `stbt.wait_until` will try one last time after the timeout is
  reached. This allows you to use a short `timeout_secs` with operations that
  can take a long time.

* Python API: The `stbt.MotionResult` object returned by `stbt.detect_motion`
  and `stbt.wait_for_motion` includes the video-frame that was analysed.
  This allows you to perform additional analysis -- for example if there was
  no motion is the frame black?

* Configuration: `global.sink_pipeline` can now be set to an empty value
  (`sink_pipeline=`). This will have the same effect as `sink_pipeline =
  fakesink` but with lower resource utilisation.


#### v27

Added HDMI CEC control; various API improvements.

16 January 2017.

##### New features

* Python API: `stbt.Region` has the following new methods: `above`, `below`,
  `right_of` and `left_of`. They return a new Region relative to the current
  region.

* New remote-control type "hdmi-cec". With the help of a USB-CEC adapter such
  as <https://www.pulse-eight.com/p/104/usb-hdmi-cec-adapter> this allows
  stb-tester to send keypresses over HDMI, to control devices that don't have
  infrared input such as Sony PlayStation.

  This remote control isn't included in the `stb-tester` Ubuntu packages we
  publish, because it uses libcec which has a GPLv2+ license (stb-tester is
  LGPL licensed). To get the CEC remote control, install the `stb-tester-gpl`
  package (currently only available for Ubuntu 16.04).

  Thanks to Daniel Andersson (@danielandersson) for the initial prototype and
  research.

##### Minor fixes and packaging fixes

* Python API: `stbt.match_text` can take single-channel images (black-and-white
  or greyscale).

* Python API: `stbt.match_text` normalises punctuation such as em-dash and
  en-dash, just like `stbt.ocr` already does.

* Python API: `stbt.match_text` has a new parameter `case_sensitive`. It
  defaults to False (that is, ignore case), which was the previous behaviour.

* Remote controls: Added `error:` remote control that raises `RuntimeError`
  when the test script calls `stbt.press`. If you don't want to use any of the
  built-in remote controls, this allows you to catch unintended uses of
  `stbt.press` in your test script. This is now the default remote control,
  instead of `none` (which ignores keypresses).

* Remote controls: Added `file:` remote control which writes keys pressed to a
  file.  Mostly intended for debugging.

* `stbt auto-selftest generate` now accepts a source filename, to generate
  self-tests for a single file instead of the whole test-pack.

* `stbt lint`: Updated to support pylint version 1.5.0 and newer (including the
  latest version as of this writing, pylint v1.6.4).

* `stbt lint`: Added FrameObject checker. It checks that FrameObject properties
  pass an explicit `frame` parameter to functions like `stbt.match`.

* Tab-completion for the command-line tools now adds trailing slashes after
  directory names.

##### Maintainer-visible changes

* Stb-tester's suite of self-tests now uses [pytest] instead of nose. The tests
  written in shell still use shell (it would be nice to port them to pytest
  too, at some point).


#### 26

New APIs to support frame-accurate performance measurements.

12 July 2016.

##### Breaking changes since 25

* We no longer provide RPM packages for Fedora. Download statistics indicate
  that everybody is using Ubuntu. Please contact the mailing list if you'd like
  to maintain the Fedora packages.

* `TextMatchResult` (returned from `match_text`) and `MotionResult` (returned
  from `wait_for_motion`) no longer derive from `tuple`. We don't expect that
  this will break any real-life test scripts.

##### New features

* Python API: `stbt.get_frame` and `stbt.frames` now return a `stbt.Frame`
  instead of a `numpy.ndarray`. `Frame` is a subclass of `numpy.ndarray` with
  an additional attribute: `time`. This is the time at which the video-frame
  was captured, as a floating point number expressed in seconds since the epoch
  (so you can compare it against Python's `time.time()`).

  The accuracy and precision of this `time` attribute depends on your
  video-capture hardware and source-pipeline configuration. See
  [this blog post](https://stb-tester.com/blog/2016/07/05/latency-measurements)
  for details on the precision guaranteed by the [stb-tester ONE] hardware.

  Note that `stbt.frames()` yields pairs of `frame, timestamp`. The `timestamp`
  element of that pair is now deprecated (it's a number in nanoseconds not
  seconds). Use the frame's `time` attribute instead.

* Python API: `MatchResult`, `TextMatchResult`, and `MotionResult` have a new
  `time` attribute. This is the time at which the matching video-frame was
  captured. The `timestamp` attribute of these classes is now deprecated. See
  the previous bullet point for details.

* Python API: `MotionResult` has a new `region` attribute which indicates where
  in the frame the motion was detected.

##### Minor fixes and packaging fixes

* The `stbt` Python package is now installed to the system Python path. This
  means that you can `import stbt` from a Python script that is run with
  `python` instead of `stbt run`. Video-capture won't work, but you can use
  `stbt.match` and `stbt.ocr` if you pass in an explicit `frame` parameter.
  This can be useful for self-tests using screenshots, and for using
  stb-tester's image-matching with other frameworks such as Selenium.

* Python API: `wait_for_motion` reports the time when the motion started, not
  the time after `consecutive_frames` of motion have elapsed.

* Python API: `MotionResult` now defines `__nonzero__`. This means you can
  write `if result:` rather than having to write `if result.motion`. This is a
  minor ergonomic improvement for consistency with `MatchResult` and
  `TextMatchResult`.

* The way motion detection is visualised on the output video has changed.
  Instead of colouring the in-motion areas red we draw a red rectangle around
  the area with motion.  This is consistent to the `match` visualisation.

* The debug log output of `match`, `wait_for_match` and `match_text` shows the
  matching region as (x, y, right, bottom) instead of (x, y, width, height).

* `stbt lint` automatically hides some useless warnings generated by
  GLib, pygobject, and libdc1394.

##### Maintainer-visible changes

* Video frames are now reference-counted, so we no longer need our `with
  numpy_from_sample` context manager when dealing with frames internally. We
  still return a *copy* from `stbt.get_frame` and `stbt.frames` because we
  haven't yet tested that users can change these frames without affecting the
  output video recording, but we intend to remove the copy in a future release.


#### 25

New features `stbt.FrameObject` and `stbt auto-selftest` that work in tandem to
make writing and maintaining tests much easier; new tool `stbt virtual-stb` for
testing any application that can run under X (instead of testing a physical
set-top box); new tool `stbt-docker` to run commands in a docker container that
has stbt installed.

3 June 2016.

##### Breaking changes since 24

* The `frame` parameter of the `MatchResult` returned from `stbt.match`,
  `stbt.detect_match` and `stbt.wait_for_match` is now read-only. Use
  `frame.copy()` if you need a writable copy.

##### New features

* Python API: New base class `stbt.FrameObject` makes it easier to structure
  your test-pack according to the Frame Object pattern. For details see the
  [stbt.FrameObject reference documentation][stbt.FrameObject] and
  [this tutorial](https://stb-tester.com/videos/example-test-script-navigating-a-menu).

* Python API: New function [stbt.match_all] that searches for *all instances*
  of a reference image within a single video frame. It returns an iterator of
  zero or more `MatchResult` objects (one for each position in the frame where
  the reference image matches).

* New tool: `stbt auto-selftest` captures the behaviour of Frame Objects and
  other helper functions that operate on screenshots, by generating doctests.

  This allows you to develop your test scripts more quickly: To implement &
  test your Frame Objects you only need some screenshots, so you don't need to
  run tests against a real set-top box to test your Frame Objects. These
  selftests will also catch unintended changes in the behaviour of your code
  when you are refactoring or changing your Frame Objects.

  For instructions see `stbt auto-selftest --help` and
  [this tutorial](https://stb-tester.com/videos/example-test-script-navigating-a-menu).

* New tool: `stbt virtual-stb` configures stb-tester to control and get its
  video from a program running on the local PC. It supports any program that
  can run under X11 (the "X Window System" used on Linux desktops). This can be
  used to test set-top box software running in emulators, or HTML5 UIs running
  in a browser. For example:

    * To test set-top box UIs during early development when the real hardware
      is not yet available.
    * As a first stage test in a continuous integration pipeline to build
      confidence in your implementation and in your tests before testing with
      real hardware. This approach can be particularly useful to reduce the
      cost of test maintenance.

  For instructions see `stbt virtual-stb --help`.

  To install on Ubuntu or Fedora, install the `stb-tester-virtual-stb` package
  (it's a separate package to avoid installing the dependencies for users who
  don't need virtual-stb). Note [known issues with virtual-stb on Fedora].

* New tool: `stbt-docker` runs the specified command in a docker container that
  is set up like an [stb-tester ONE] but without video-capture or infrared
  hardware.

  The docker container will have stbt and all its dependencies installed, as
  well as your test-pack's own dependencies as specified in
  [config/setup/setup]. This makes it easier to run stbt commands on a CI
  server or on a developer's PC for local test-script development, when
  video-capture is not needed: For example to run pylint, stbt auto-selftest,
  etc.

  stbt-docker is built with portability in mind so it should run on Mac OS and
  Windows. The only dependencies are Python and Docker. stbt-docker is
  self-contained and relocatable so it can be deployed as a single file with no
  dependency on anything else in stbt.

  stbt-docker development is done in its own git repository:
  <https://github.com/stb-tester/stbt-docker>. See the README file there for
  usage & installation instructions.

* The `stbt templatematch` command-line tool has been renamed to `stbt match`
  (for consistency with the Python API terminology). The old name remains as an
  alias, for backwards compatibility.

* New `roku` remote control that uses the [Roku HTTP control protocol].
  Stb-tester's [standard key names] (like "KEY_HOME") will be converted to the
  corresponding Roku key name, or you can use the [Roku key names] directly.
  For configuration instructions see the documentation for `--control` in the
  [stbt(1) man page].

* The `x11` remote control now converts stb-tester's [standard key names] (like
  "KEY_UP") to the key names that `xdotool` expects. This allows you to run the
  same test scripts (without needing to change the key names) against a real
  set-top box and against an emulator running under `stbt virtual-stb`. You can
  also now specify a custom mapping of key names (see the [stbt(1) man page]).

* The `stbt camera` calibration videos have been modified to use QR codes
  rather than text and OCR.  This makes calibration faster, but will require
  the videos to be re-generated on first use.

* `stbt camera` learned how to control Android TVs over adb for calibration.

##### Minor fixes and packaging fixes

* When `match` and `wait_for_match` can't find the specified reference image,
  the error message now says the actual path & filename you specified (that is,
  a path relative to the test script), not an absolute path under the current
  working directory.

* `match_text` now logs a line (when debug output is enabled) saying whether it
  found a match or not, much like `match` and `wait_for_match` already do.
  Thanks to Rinaldo Merlo for the patch.

* The "stb-tester" packages for Ubuntu & Fedora no longer install the
  dependencies for the x11 remote control; they are installed by the
  "stb-tester-virtual-stb" package instead.

[stbt.FrameObject]: https://stb-tester.com/manual/python-api#stbt.FrameObject
[stbt.match_all]: https://stb-tester.com/manual/python-api#stbt.match_all
[known issues with virtual-stb on Fedora]: https://github.com/stb-tester/stb-tester/issues?q=is%3Aissue+virtual-stb
[stb-tester ONE]: https://stb-tester.com/stb-tester-one
[config/setup/setup]: https://stb-tester.com/manual/advanced-configuration#customising-the-test-run-environment
[Roku HTTP control protocol]: https://sdkdocs.roku.com/display/sdkdoc/External+Control+Guide
[standard key names]: https://stb-tester.com/manual/getting-started#remote-control-key-names
[Roku key names]: https://sdkdocs.roku.com/display/sdkdoc/External+Control+Guide#ExternalControlGuide-3.4ValidKeys
[stbt(1) man page]: https://github.com/stb-tester/stb-tester/blob/master/docs/stbt.1.rst


#### 24

Updated to work with Ubuntu >= 14.10 and Fedora >=21; and many small additions,
bugfixes, and improvements.

13 January 2016.

##### Breaking changes since 23

* `stbt lint` no longer works with pylint < 1.0. If your distro provides an
  older pylint, we recommend installing a newer pylint from PyPI.

##### User-visible changes since 23

* Work around a regression in PyGObject 3.13 (#305). This will allow stb-tester
  to work out of the box on Ubuntu >= 14.10 and Fedora >= 21.

* Updated `stbt.match_text` to work with tesseract 3.04 (Ubuntu >= 15.10 and
  Fedora >= 23).

* Python API: New method `stbt.Region.replace` to set any of the edges of a
  region to the given coordinates. It is similar to `stbt.Region.extend`, but
  it takes absolute coordinates within the image instead of adjusting the edge
  by a relative number of pixels.

* Python API: `stbt.wait_for_match` and `stbt.detect_match` take an optional
  `region` parameter, just like `stbt.match` already did.

* Python API: `stbt.match_text` now adds the expected text to tesseract's
  dictionary, which fixes some false negatives.

* Python API: Bug fix: `stbt.wait_until` no longer raises an exception if you
  passed a `functools.partial` object (or an instance of a class with a
  `__call__` method) and `wait_until` timed out. Thanks to Martyn Jarvis for
  the patch.

* Python API: You can now raise an exception with unicode in the exception's
  message. Previously the testrun's failure reason would show a
  "UnicodeEncodeError" instead of your actual exception message.

* The video-recording of a test run will show the name of the image that
  `stbt.wait_for_match` is searching for. Thanks to Lewis Haley for the patch.

* `stbt run` will now save a screenshot at the end of all failing test runs,
  rather than just those which failed due to an exception with a screenshot
  attached.

* The screenshot that `stbt batch run` saves is more likely to be relevant to
  the issue seen. Now we save the last frame that the test-script saw;
  previously we took a new screenshot at some point soon after the test-run had
  completed.

* `stbt batch run`: New `--no-html-report` option to disable HTML report
  generation. Normally `stbt batch run` generates an HTML report before each
  testrun (so that the report shows a "running..." row for the current test)
  and again after the testrun (to update that row with the test's result). This
  report generation gets slower as you have more results because it scans all
  the results in the output directory each time. If you have your own reporting
  system, this report generation is superfluous. Apart from the "index.html"
  inside the testrun directory and the "index.html" one directory above it (at
  the root of the output directory), no other files are affected. That is, the
  result format on disk won't change (this on-disk result format is a public,
  stable API). You can still generate the HTML reports afterwards with `stbt
  batch report`.

* `stbt batch run` wasn't generating HTML reports if you gave it an `--output`
  directory name with spaces.

* `stbt lint` will complain if you don't use the return value from
  `is_screen_black`, `match`, `match_text`, `ocr`, or `wait_until`. When the
  return value from `wait_until` isn't used in an `if` statement or assigned to
  a variable, you've probably forgotten to use `assert`.

* `stbt lint` will complain if the argument to `wait_until` isn't callable
  (such as a function or a lambda expression). This will catch mistakes like
  `wait_until(is_screen_black())` when you meant to say
  `wait_until(is_screen_black)`.

* `stbt lint` no longer complains if the filename given to `cv2.imwrite`
  doesn't exist.

#### 23

New `stbt batch run --shuffle` option to run test cases in a random order.

10 July 2015.

##### User-visible changes since 22

* `stbt batch run` learned a new option: `--shuffle`. The `--shuffle` option
  runs the given test cases in a random order.  This can be useful if you have
  structured your test pack as a large number of short targeted tests.  You can
  then use:

        stbt batch run --shuffle \
            epg.py::test1 epg.py::test2 menu.py::test1 menu.py::test2 ...

  to attempt a random walk of different journeys though your set-top-box UI.
  This can be particularly effective at finding hard to trigger bugs and get
  more value out of the test-cases you have written.

  Some tests may take much longer than other tests, which will then use up a
  disproportionate amount of your soaking time.  To work around that we measure
  how long each test takes the first time it is run, and use that as a weighting
  when choosing the next test to run attempting to equalise the time spent in
  each test case.

  This makes it reasonable to include both tests that take 10s and tests that
  take 10min in the same random soak.

* There is new structured logging/tracing infrastructure allowing monitoring
  what `stbt run` is doing in real-time and saving this data for replay and
  analysis later.  `stbt run` will write this data to file if it is given the
  `--save-trace` command-line option and will write it to the unix domain socket
  given by the `STBT_TRACING_SOCKET` environment variable.

  This is used by the stb-tester ONE to display the current status of the
  executing test.  The tools for replay have not yet been written.  For more
  information, including the format definition see `_stbt/state_watch.py`.

* The text drawn by `stbt.draw_text` and `stbt.press` on the recorded video now
  fades out over a few seconds. This makes it easier to distinguish the new
  messages from the old messages.

##### Maintainer-visible changes since 22

* Much of the code has moved from `stbt/__init__.py` to `_stbt/core.py`. This
  is part of the work in progress to allow `stbt` to be used as a library from
  other Python code without having to use `stbt run`.

* `stbt batch run` has been partially rewritten in Python for better
  maintainability and extendability.

* `stbt batch run` now uses process groups to keep track of its children, rather
  than just using the process heirarchy.

* Support for the ATEN network-controlled power supply has been rewritten in
  Python (from bash). (Thanks to Martyn Jarvis and YouView for the patch.)

#### 22

Support for testcases as Python functions and using *assert* in testcases; new
*wait_until* function; improved report formatting; support for the *Aviosys USB
Net Power 8800 Pro* power outlet.

27 March 2015.

Note: The version numbering scheme has changed from this release onwards.
Instead of "0.22" this is version "22". Stb-tester has been usable, stable,
backwards-compatible software for years now so carrying a "0." is misleading
and adds no information.

##### Breaking changes since 0.21

* `stbt run` will now set the encoding of stderr and stdout to utf-8 when
  writing to a file or pipe (or otherwise not connected to a terminal with
  `LANG` set) rather than defaulting back to ASCII. This makes the behaviour
  more consistent between using `stbt run` (interactively) and `stbt batch run`
  which logs to a file. Previously a `UnicodeEncodeError` would be `raise`d
  when `print`ing a unicode string like `print u"Alfonso Cuarón"`.

  This is the same (sensible) behaviour that Python 3 has by default.

* `stbt run` and `stbt batch run` treat `AssertionError`s as test failures, not
  test errors. Along with the introduction of `match` in stb-tester 0.21 and
  `wait_until` in this release, this provides a more composable API. See the
  documentation for `wait_until` for more details.  `stbt` functions now
  (correctly) raise `ValueError` if the arguments passed are incorrect rather
  than checking for correctness with `assert`.

* `stbt record` now creates python files with the testcase in a Python function
  instead of at the top level of the file. See the change to `stbt run` in the
  next section for more details.

* `MatchResult.image` now returns the template image name as passed to
  `stbt.match`, rather than the absolute path to the template.  This is the
  previously documented behaviour and allows constructs like:

        m = stbt.wait_until(
            lambda: stbt.match("success.png") or stbt.match("error.png"))
        assert m
        if m.image == "error.png":
            recover()

* Removed the `noise_threshold` parameter of `wait_for_match`, `detect_match`
  and `press_until_match`. This parameter had been deprecated for almost two
  years, since stb-tester 0.13.

* `stbt power status` now always requires the outlet to be explicitly specified
  for network controlled PDUs, rather than printing the statuses of each outlet
  in some implementation-dependent format.

##### User-visible changes since 0.21

* `stbt run` and `stbt batch run` can now run a specific Python function in the
  test file if you give the testcase name as
  `test_file_name.py::test_function_name`.

  For example, if you have a file `test.py` that looks like this:

        import stbt

        def test_that_logo_is_shown():
            stbt.wait_for_match("logo.png")

        def test_that_menu_appears():
            stbt.press("KEY_MENU")
            stbt.wait_for_match("menu.png")

  ...then you can run one of the tests like this:

        stbt run test.py::test_that_logo_is_shown

  This has several advantages over the existing one-test-per-file approach:

    * It encourages smaller, more descriptive testcases.
    * It makes it easier to factor out and share common code between testcases.
    * You can attach documentation or metadata to testcases (using docstrings,
      `nose.plugins.attrib.attr`, etc.) which can be queried by importing the
      test file and inspecting the functions.
    * It is the same approach used by [nose] and [pytest] which opens doors in
      the future to make use of facilities that these test frameworks provide.
      See [our blog post](
      http://stb-tester.com/blog/2014/09/25/upcoming-features-new-test-runner.html)
      for some possible future directions.

  This is the format we recommend going forward (of course the old format is
  still supported). We have used this format exclusively for 6+ months in a
  client's project and it works well. The *stb-tester <small>ONE</small>*
  appliance requires this format.

  We recommend that you name your testcase functions to start with "test_", for
  future compatibility with test frameworks like [nose] and [pytest].

* The video that is saved by `stbt run --save-video` and `stbt batch run` now
  displays the wall-clock time at the top of each frame. This makes it easier
  to relate timestamps from the logfiles with the video. (Thanks to Dariusz
  Wiatrak, Máté Szendrő, and YouView for the patch.)

* The text drawn on the video that is saved by `stbt run --save-video` and
  `stbt batch run` now uses a more legible font and background, to make it
  easier to read.  (Thanks to Máté Szendrő and YouView.)

* API: New function `wait_until` runs any given function or lambda expression
  until it succeeds, or until a timeout. This provides the waiting behaviour of
  `wait_for_match`, but more general -- you can use it to look for a match or
  the absence of a match, you can use it with `match_text`, `is_screen_black`,
  user-defined functions, etc. See the [API documentation](
  http://stb-tester.com/stbt.html#wait_until) for more details.

* report: The `stbt batch run` report now uses a logarithmic y-axis for test
  duration, so the graph is still readable when there are very long test runs
  alongside shorter ones.

* report: Improved table layout so that it doesn't overflow into the right-hand
  details pane if the window is too small. We don't allow table rows to
  overflow, so the row height for each testrun is consistent and neater. We
  also truncate the cell contents (such as the failure-reason column) using
  CSS instead of truncating it in the HTML; this allows the full text of the
  table cell to be searchable from the search box at the top of the report.

* API: `is_screen_black()` now no longer requires a frame to be passed in.  If
  one is not specified it will be grabbed from live video, much like `match()`.

* `stbt power`: Added support for "Aviosys USB Net Power 8800 Pro"
  USB-controlled power outlets.

[nose]: https://nose.readthedocs.org/
[pytest]: http://pytest.org/latest/

##### Bugfixes and packaging fixes since 0.21

* `stbt camera calibrate` no longer hangs during colour calibration ([#264])

* report: Fixed filtering results for columns where the first row could be
  confused as a date, because the date matching regex was too broad.

* `stbt batch run` will no longer skip tests if the test-script reads data on
  stdin.

[#264]: https://github.com/stb-tester/stb-tester/issues/264

##### Maintainer-visible changes since 0.21

* `stbt power` is now implemented in Python rather than bash, although for the
  time being it still calls back into the bash implementation to control/query
  the ATEN, IP Power 9258 and PDUeX KWX outlets.  Users of these PDUs are
  encouraged to contribute Python implementations and automated tests for these
  devices.

#### 0.21

Composable API, match_text, stbt camera, triaging improvements

12 Dec 2014.

##### Breaking changes since 0.20

* The internal representation of `Region` has changed from (x, y, right, bottom)
  to (x, y, width, height). The constructor `Region(x, y, width, height)`, and
  the `width` and `height` properties, remain for backward compatibility, so
  this is not intended as an externally visible change. However, some details
  may leak through the cracks. These include:

    * The string returned by `__repr__` lists right and bottom rather than
      width and height.  This is necessary as `repr` should be unambiguous.
    * If you use subscripting to get at the internal representation of the
      `Region` (e.g. `region[2:]`) this will now return `right` and `bottom`.

* `stbt batch run` now exits with non-zero exit status if any of the tests in
  the run failed or errored.  In addition if only a single test was executed a
  single time `stbt batch run` will propogate the exit status through.  This, in
  combination with the `-1` option makes it easier to use from and integrate
  with external CI systems and makes it possible to use `stbt batch run` as a
  better `stbt run`.

* `stbt.ConfigurationError` now inherits from `Exception` instead of
  `stbt.UITestError`. (In future we may replace `UITestError` throughout stbt
  -- see <https://github.com/stb-tester/stb-tester/pull/86>.)

##### User-visible changes since 0.20

* Added new API `stbt.match` which was previously conspicuous in its absence.
  It checks a single frame of video and returns a `MatchResult`.

  `MatchResult`s can now be treated as a boolean. Together, this makes it much
  easier to compose matching operations in user code. For example:

        assert stbt.match('template.png') or stbt.match('template2.png')

* Added new API `stbt.match_text` to match text using OCR. It takes a string
  and returns a `TextMatchResult`, much like how `stbt.match` takes an image
  filename and returns a `MatchResult`. The `TextMatchResult` can be treated as
  a boolean, and it provides additional information such as the region of the
  match. It should be very helpful for UIs which consist of menus of text,
  which seem to be most UIs.

* Added experimental support for testing TVs by capturing video from a camera.
  Install the `stb-tester-camera` package and use `stbt --with-experimental` to
  enable. We call it "experimental" because in the future we intend to change
  some aspects of the implementation, the calibration process, the command-line
  API, and the configuration options. For instructions see
  <https://github.com/stb-tester/stb-tester/blob/master/stbt-camera.d/README.md>.

* Added new "x11" remote-control type for sending keypresses to an X display.
  It can be used with GStreamer's ximagesrc for testing desktop applications
  and websites. For details see the documentation for `--control` in the
  [stbt(1) man page].

* The videos recorded by `stbt batch run` are now shown inline in the HTML
  report using the HTML5 video tag. This looks great and makes triage easier.

* The search/filter functionality of the `stbt batch` html reports is now
  hooked up to the URL's querystring, so you can share a link to a subset of
  the report.

* `stbt batch run` has a new `-o` flag to specify the output directory where
  you want the report and test-run logs to be saved. If not specified it
  defaults to the existing behaviour, which is to write to the current working
  directory.

* The `STBT_CONFIG_FILE` environment variable can now specify multiple config
  files, separated by a colon. Files specified earlier in the list are searched
  first.

* `Region` now has convenience methods `extend` and `translate` and the
  function `intersect` to make it easier to receive a region, modify it and
  then pass it to another function.

* `Region.ALL` represents the entire 2D frame from -∞ to +∞ in both the x and y
  directions. This is useful to pass to functions that take a `region=`
  parameter to say that we want the whole frame considered.

  In 0.20, `stbt.ocr`'s `region` parameter defaulted to `None`, which meant to
  use the whole image for OCR. `Region.ALL` is the new default value with the
  same meaning. Passing `region=None` to `ocr` is still supported but
  deprecated; in the future we may change its meaning to mean the empty region,
  for consistency with `Region.intersect`.

* The `MatchResult` object returned by `match` and `wait_for_match` now
  includes the region of the match, not just the top-left position. This makes
  it convenient to pass the region to other functions, for example to read the
  text next to an icon:

        m = stbt.wait_for_match('icon.png')
        text = stbt.ocr(region=m.region.extend(right=200))

* `is_screen_black` logs debug images to `stbt-debug` when additional debugging
  is enabled with `stbt run -vv`, similar to `wait_for_match` etc.

* The location of the keymap file used by the interactive `stbt control`
  command can now be specified in the `control.keymap` configuration key.
  Previously this could only be specified on the `stbt control` command line,
  with `--keymap`. It still defaults to `~/.config/stbt/control.conf`.

* `stbt.press` and `stbt.draw_text` now draw a black background behind the text
  drawn to the saved video, so that the text is legible against light
  backgrounds.

##### Bugfixes and packaging fixes

* `stbt.debug` no longer raises `UnicodeEncodeError` when writing a unicode
  string and `stbt`'s output is redirected to a file. This was most visible
  when `stbt.ocr`, which calls `stbt.debug` internally, was finding non-English
  text.

* Fixed using `stbt.ocr`'s optional `tesseract_config`, `tesseract_user_words`
  and `tesseract_user_patterns` parameters on Fedora. Previously, attempting
  to use these would raise a RuntimeError saying "Installation error: Cannot
  locate tessdata directory".

* Fixed `stbt run` crash when using GStreamer 1.4.

* `stbt batch run` can now store results in a VirtualBox shared folder (or
  similar filesystems that don't allow fifos).

* The Fedora package now installs `libvpx` if it's missing -- we need it for
  the videos recorded by `stbt batch run` and `stbt run --save-video`.

##### Maintainer-visible changes since 0.20

* The `stbt.py` python module has been split into a python package
  (`stbt/__init__.py`, `stbt/config.py`, etc). This is for code organisation
  and (in future) flexibility in deployment. Users of the public API (that is,
  test scripts) should continue to use the same API (for example
  `stbt.get_config` not `stbt.config.get_config`).

* `stbt.ocr` now honours the `TESSDATA_PREFIX` environment variable, so you can
  test a locally-built version of tesseract.

#### 0.20

Stb-tester ported to GStreamer 1; OCR accuracy improvements

6 Jun 2014.

For upgrade instructions from 0.18, see the release notes for the 0.19 beta
release.

Thanks to Lewis Haley and Máté Szendrő for extensive testing, bug reports, and
patches.

##### Breaking changes since 0.19 beta

* `stbt.ocr` returns a unicode object rather than a string.
* Note that 0.19 beta introduces significant breaking changes (to your stbt
  configuration files, not to your test scripts) from 0.18; see the 0.19 beta
  release notes for details.

##### User-visible changes since 0.19 beta

Changes to the Python API:

* Improvements to OCR (optical character recognition):
    * Accuracy improvements (see
      [this blog post](http://stb-tester.com/blog/2014/04/14/improving-ocr-accuracy.html)
      for details).
    * Callers of `stbt.ocr` can specify the expected language.
    * Callers of `stbt.ocr` can pass custom dictionaries and custom patterns
      to tesseract (the OCR engine that stb-tester uses).
    * Callers of `stbt.ocr` can fine-tune any of tesseract's paramaters.
      Note that the effect, and even existence, of these parameters can
      vary from one version of tesseract to another.
    * For details see the
        [`stbt.ocr` API documentation](http://stb-tester.com/stbt.html#ocr)
        and [OCR Tips](http://stb-tester.com/ocr.html).
    * `stbt.ocr` debug (enabled with `stbt run -v`) reports the region
      you specified.
    * `stb-tester/tests/validate-ocr.py` is a script that you can use to
      measure the effect of changing OCR parameters against your own private
      corpus of test screenshots.
* `stbt.Region` has new convenience methods to create a Region from x & y
  coordinates instead of width & height, and to check if a Region is contained
  within another. For details see the
  [`stbt.Region` API documentation](http://stb-tester.com/stbt.html#Region).
* `stbt.debug` output is now UTF-8.

Changes to the command-line tools:

* Improve `stbt run` latency on slow computers and after video-capture device
  restarts ([issue #137](https://github.com/stb-tester/stb-tester/issues/137),
  introduced in 0.19).
* `stbt power` supports the ATEN brand of network-controlled power distribution
  units (thanks to Aiman Baharna).
* `stbt tv` fixed on OS X (broken in 0.19 in the port to GStreamer 1).
* `stbt lint` gives a better error message when no arguments are given.
* `stbt control` no longer needs `nose` (a python testing tool) to run.
  (Dependency introduced in 0.19.)
* `stbt screenshot` skips the first frame, because some V4L video-capture
  hardware delivers a single black frame before the real video stream.
* `stbt batch run` classifies Blackmagic Intensity Pro problems correctly
  (broken in 0.19).
* Fixed deprecation warning printed by `stbt templatematch` (introduced in
  0.19).
* `stbt run` with `GST_DEBUG_DUMP_DOT_DIR` defined will now dump the debugging
  information for the appropriate pipeline. Previously we dumped debugging
  information for the source pipeline, even if the error came from the sink
  pipeline.
* All `stbt run` debug output is UTF-8.
* `stbt run -vv` image-matching debug output shows more precise values for
  the threshold of the first pass of the image processing algorithm.

Other changes:

* The report generated by `stbt batch` has improved the presentation of the
  currently-selected row: Instead of highlighting it in blue, you can still see
  the green/red/yellow colour so you can tell whether that test-run passed or
  failed.
* The Virtual Machine creation script in `extra/vm/` is now based on Ubuntu
  14.04 (instead of 12.04) and installs stb-tester 0.20 from the Ubuntu PPA
  (instead of installing the version of stb-tester from your source checkout on
  the host machine).
* Ubuntu packaging fixes: The stb-tester package now installs lsof (used by
  `stbt batch run` if you're using the Blackmagic Intensity Pro video-capture
  card), gstreamer1.0-libav (for H.264 decoder if you're using a video-capture
  device that provides H.264-encoded video; on Fedora you have to install this
  manually from rpmfusion), and the tesseract-ocr English language data.
* Fedora packaging fixes: The stb-tester package now installs lsof,
  gstreamer1-plugins-bad-free-extras (for the GStreamer `decklinksrc` element
  for the Blackmagic Intensity Pro).

##### Maintainer-visible changes since 0.19 beta

* `make check` now passes with pylint 1.x (and it continues to pass with pylint
  0.x).
* The tarball generated by `make dist` is more deterministic (running `make
  dist` twice should now result in tarballs with the same checksum --
  at least when running `make dist` on the same machine).

#### 0.19.1

BETA RELEASE: Packaging fixes to 0.19

9 Apr 2014.

The 0.19 pre-built package wouldn't install on Fedora 19. Fedora 20 users are
unaffected.

#### 0.19

BETA RELEASE: Stb-tester ported to GStreamer 1.

4 Apr 2014.

**0.19 is a beta release that is incompatible with your existing
`source_pipeline` (and possibly `sink_pipeline`) configuration.**
No changes are needed to your test scripts themselves.

Please test this release and give us your feedback on the
[mailing list](mailto:stb-tester@googlegroups.com).

##### Installation instructions on Fedora 19 or 20

Fedora pre-built packages have moved from the
[OpenSuse Build Service](http://software.opensuse.org/download.html?project=home%3Astb-tester&package=stb-tester)
to [Fedora Copr](https://copr.fedoraproject.org/coprs/stbt/stb-tester/)
(a new service from Fedora similar to Ubuntu's PPAs).

This means that existing users of stb-tester won't accidentally upgrade to an
incompatible version if they do `yum upgrade`. All future versions of
stb-tester will be released via Fedora Copr.

* Remove your existing stb-tester yum repository (if applicable):

        sudo rm /etc/yum.repos.d/home:stb-tester.repo

* Add the appropriate Copr repository. For Fedora 20:

        sudo wget -O /etc/yum.repos.d/stb-tester.repo \
            https://copr.fedoraproject.org/coprs/stbt/stb-tester/repo/fedora-20-i386/

    or for Fedora 19:

        sudo wget -O /etc/yum.repos.d/stb-tester.repo \
            https://copr.fedoraproject.org/coprs/stbt/stb-tester/repo/fedora-19-i386/

* Install stb-tester:

        sudo yum install stb-tester

##### Installation instructions on Ubuntu 13.10

Starting from stb-tester 0.19 we provide pre-built packages for Ubuntu 13.10.
If you had previously installed stb-tester from source, remember to uninstall
that version.

    sudo apt-get install software-properties-common  # for "add-apt-repository"
    sudo add-apt-repository ppa:stb-tester/stb-tester
    sudo apt-get update
    sudo apt-get install stb-tester

##### Configuration changes

See
["Porting from GStreamer 0.10 to GStreamer 1.0"](https://github.com/stb-tester/stb-tester/blob/master/docs/backwards-compatibility.md#porting-from-gstreamer-010-to-gstreamer-10)
in the stb-tester documentation.

##### Known issues

The HDPVR doesn't work with GStreamer 1's gst-plugins-good < 1.2.4.

As of this writing, 1.2.4 hasn't been released yet, so we have provided patched
gstreamer1-plugins-good packages for Fedora 19 and 20 at the above Copr
repository.

See also the [list of known issues on github](
https://github.com/stb-tester/stb-tester/issues?labels=0.19).

##### Breaking changes

* Stb-tester ported to GStreamer 1.

    GStreamer 1 has been out for a year and a half now. The previous version of
    GStreamer, 0.10, is unsupported by the GStreamer project and thus no longer
    receives new features or bug fixes.

    GStreamer 1 isn't ABI or API compatible with GStreamer 0.10, but the only
    thing that stb-tester users need to change is their `source_pipeline`
    configuration. See
    ["Porting from GStreamer 0.10 to GStreamer 1.0"](https://github.com/stb-tester/stb-tester/blob/master/docs/backwards-compatibility.md#porting-from-gstreamer-010-to-gstreamer-10)
    in the stb-tester documentation.

* `stbt run` passes optional arguments after script name to the script.

    Previously the following command-line would pass `--source-pipeline=...` to
    `stbt run`:

        stbt run test.py --source-pipeline=videotestsrc

    ...whereas now `--source-pipeline=...` will be passed to the test script
    `test.py`. Options to `stbt run` must be passed *before* the test script
    name, like this:

        stbt run --source-pipeline=videotestsrc test.py

    This change allows test scripts to take optional arguments of their own.

##### Other major new features

* The template image passed to `wait_for_match` and `detect_match` can be an
  OpenCV image (that is, a numpy array). This allows template images to be
  created on-the-fly without having to write intermediate image files to disk.
  See commit [2c276e36] for some example uses.

* Setting the `GST_DEBUG_DUMP_DOT_DIR` environment variable will dump a graph
  of your GStreamer pipeline if an error occurs. This is useful for debugging
  problems in your `source_pipeline` configuration. See commit [7b3eaf33] for
  details.

* New "samsung" control that can be used instead of an infrared emitter to
  control recent Samsung Smart TVs. Use `control=samsung:<hostname>` in the
  `global` section of your configuration file.

##### Minor changes

* `stbt.as_precondition` preserves the screenshot from intercepted failures.
* `stbt.ocr` doesn't print "Tesseract Open Source OCR Engine v3.02.02 with
  Leptonica" to standard error.
* Text read by `stbt.ocr` is printed when debug logging is enabled (with `stbt
  run -v`).
* `stbt.MatchTimeout` and `stbt.MotionTimeout` error messages show timeout
  values smaller than 1 (previously they would show "0" instead of, for
  example, "0.5").
* `stbt.wait_for_match` per-frame debug output includes the template filename.
* The html debug visualisation created by `stbt run -vv` shows the
  region-of-interest found by the first pass of the image-matching algorithm.
* `stbt control` detects duplicate keyboard keys in the keymap file.
* `stbt lint` doesn't refuse to work with pylint 1.x.
* `stbt lint` doesn't consider the string `".png"` (on its own) as a missing
  image file.
* `stbt power` returns the correct exit status when given invalid outlet.
* `stbt batch run` supports test scripts not in a git repository.
* `stbt batch run` only saves a screenshot if `stbt run` didn't already save
  one from a `MatchTimeout` exception.
* `stbt batch run -t` supports tags containing spaces (you'll have to quote the
  tag so that the shell passes the entire string including spaces as the
  argument to `-t`: `stbt batch run -t "my tag" ...`).
* If you interactively edit the "failure reason" or "notes" field in the
  reports hosted by `stbt batch instaweb`, the main table is updated
  immediately.
* The Fedora package installs missing dependencies for `stbt batch run` and
  `stbt batch instaweb`.
* The Fedora package doesn't overwrite a user-modified `/etc/stbt/stbt.conf`.

Thanks to Lewis Haley, Máté Szendrő, and Pete Hemery for their contributions to
this release.

#### 0.18

Bulk test runner & reporting; text recognition (OCR)

28 Jan 2014.

New tool `stbt batch` runs stb-tester scripts (once, or repeatedly if
you want a soak test) and generates an interactive html report. For
documentation and an example of the report see
<http://stb-tester.com/runner.html>; see also `stbt batch --help` and
<https://github.com/stb-tester/stb-tester/blob/0.18/stbt-batch.d/README.rst>.
This was previously available in the source distribution under
`extra/runner`; now it is installed as `stbt batch` by `make install`
and the RPM.

New python function [`stbt.ocr`](http://stb-tester.com/stbt.html#ocr)
performs Optical Character Recognition and returns a string containing
the text present in the video frame.

New python function
[`stbt.is_screen_black`](http://stb-tester.com/stbt.html#is_screen_black)
checks for a black screen (with an optional mask). This is useful for
measuring the time between channel changes. See the unit test
[test_using_frames_to_measure_black_screen](https://github.com/stb-tester/stb-tester/blob/0.18/tests/test-stbt-py.sh#L96)
for an example of usage.

New python function
[`stbt.as_precondition`](http://stb-tester.com/stbt.html#as_precondition)
to help manage which errors appear as failures (red) or as errors
(yellow) in the report generated by `stbt batch`. For more details see
<http://stb-tester.com/precondition.html>.

`stbt.press` now takes a new optional parameter `interpress_delay_secs`
to ensure a minimum delay between subsequent key presses. This is to
accommodate systems-under-test that don't register infrared signals if
they are sent too closely together. The default value is read from
`press.interpress_delay_secs` in the stbt configuration file, and
defaults to `0.0`.

Minor changes:

- When `wait_for_match` raises a `MatchTimeout` exception, the
  `screenshot` member of the exception object is the exact frame that
  `wait_for_match` saw. (Previously, the `screenshot` was a frame
  captured slighly afterwards.) This also affects the screenshot saved
  by `stbt run` when the script terminates due to an unhandled `MatchTimeout`
  exception.

- Fixed incorrect first-pass "matched" text in the match-related debug
  [visualisation](http://stb-tester.com/stbt-debug-example/detect_match/00001/)
  created in `stbt-debug/` by `stbt run -vv` or `stbt templatematch -v`.

- The tab-completion for `stbt templatematch` correctly completes the
  possible values for the `match_method` and `confirm_method` arguments.

#### 0.17

Image matching optimisation; support for Teradek VidiU;
`stbt.press_until_match` configuration; html summary of debug images; `stbt
lint`; `stbt tv -l`.

17 Dec 2013.

Major user-visible changes:

- `stbt.wait_for_match` and `stbt.detect_match` are now much faster in
  most cases (6 to 12 times faster according to my measurements), thanks
  to a performance optimisation called "pyramid matching" where
  scaled-down versions of the video frame and reference image are
  compared first to narrow down the region of interest for the match
  algorithm at the full-sized resolution. This optimisation is enabled
  by default; it shouldn't affect the behaviour, but you can disable it
  by setting `match.pyramid_levels` in your configuration file to `1`.

- `stbt run` end-of-stream handling to better support the behaviour of
  the Teradek VidiU, a video-capture device that delivers an RTMP stream
  over the network.

- `stbt.press_until_match` parameters `interval_secs` and `max_presses`
  can be set globally in your configuration file, in section
  `[press_until_match]`. Being able to change `interval_secs` without
  updating all your scripts is useful because `press_until_match` can be
  sensitive to timing issues, depending on your hardware configuration.
  See commit [e1a32b97] for details.

- The debug images generated by `stbt run -vv` or `stbt templatematch
  -v` are now supplemented by an HTML file that serves as a guide to
  understanding the images.

- `stbt lint` is a new tool that runs pylint over stb-tester scripts,
  with a custom pylint plugin that checks image paths given to
  `stbt.wait_for_match` (and similar functions) to ensure that the
  images exist on disk. See commit [96afe36d] for details on
  using `stbt lint` and on configuring pylint. Requires pylint 0.x (as
  of this writing, pylint 1.0 contains serious bugs and
  incompatibilities).

- `stbt tv -l` will stream live video to another computer on the network;
  see `stbt tv --help` for details.

Minor user-visible changes and bugfixes:

- `stbt.get_config` takes a `type_` parameter, and raises
  `ConfigurationError` if the specified configuration value cannot be
  converted to the specified type.

- `stbt.MatchParameters` checks the values given for `match_method` and
  `confirm_method` (previously, unexpected values of `confirm_method`
  were being treated as "absdiff").

- Improved error messages when the reference image is larger than the
  source video frame.

- Fix an uncommon null dereference error when `stbt run` is tearing down.

- When the video-capture device is a Blackmagic Intensity Pro, `stbt
  screenshot` first captures a few seconds of video before taking the
  screenshot; Blackmagic cards have a known defect where the first few
  frames of video have a magenta or purple tint.

- `stbt tv` will display the correct aspect ratio on screens smaller
  than the video stream.

- `stbt power` now uses the HTTP interface of PDUeX network-controlled
  power supply units, instead of the SSH interface. This is to avoid
  lock-ups of the SSH interface, where it consistently refuses to accept
  connections after about a week of uptime.

Changes to the `extra` scripts in the source code repository:

- Added plot of testrun durations to the HTML report generated by the
  bulk test-runner script in `extra/runner`.

- Display Wilson Score confidence intervals instead of a single
  percentage, in the HTML report.

- Minor bugfixes and usability improvements to the bulk test-runner
  script and report.

- The Virtual Machine setup scripts in `extra/vm` install and configure
  an RTMP server, for users of Teradek VidiU video-capture hardware.

Changes visible to developers of stb-tester:

- `make check` uses fakesink instead of ximagesink, so it doesn't pop
  up lots of X Windows that interfere with your typing.

- `tests/run-tests.sh` accepts a test-suite filename as a command-line
  argument, to run just the self-tests in that file (for example
  `run-tests.sh test-motion.sh`).

- Self-tests can now return 77 to indicate a skipped test.

- Fixed some race conditions in the self-tests.

#### 0.16

*stbt.wait_for_motion* configuration; *stbt.draw_text*; *stbt.press* error
handling; *stbt run --restart-source* flag; irNetBox proxy

4 October 2013.

The default values for the *noise_threshold* and *consecutive_frames*
parameters to *stbt.wait_for_motion* and *stbt.detect_motion* can now
be set globally in the stbt configuration file. See the [API
documentation](http://stb-tester.com/stbt.html#test-script-format) for
details.

*stbt.draw_text* overlays the specified text on the video output. It is
much easier to understand a test run if the video contains descriptions
like "about to reboot" or "navigating to menu X". Note that since 0.15,
*stbt.press* draws the name of the pressed key on the video; now we
expose the same functionality to user scripts.

*stbt.press* now waits for a reply from the underlying LIRC or irNetBox
hardware before returning, and raises *Exception* if the reply timed out
or indicated an error.

The *global.restart_source* configuration item is now documented, and
can also be enabled on the *stbt run* or *stbt record* command line
(with *--restart-source*). This causes the GStreamer source pipeline to
be restarted when no video is detected for 10 seconds, to work around
the behaviour of the Hauppauge HD PVR video-capture device upon HDMI
renegotiation or other transient loss of input video signal.

*irnetbox-proxy* is a new utility to overcome a limitation of the RedRat
irNetBox network-controlled infrared emitter. *irnetbox-proxy* behaves
like a real irNetBox, except that unlike a real irNetBox it accepts
multiple simultaneous TCP connections from different clients (and
forwards requests to a real irNetBox over a single TCP connection).

*stbt templatematch* is around \~10x faster (only the command-line tool,
not image matching in *stbt run*).

Python scripts run with *stbt run* can now access their real path in
*\_\_file\_\_* and can import modules from the script's own directory
(the same behaviour you get when you run a python script directly with
*python*).

#### 0.15

*stbt power*; *stbt control* can be used with *stbt record*; test scripts can
take command-line arguments; *stbt.press* shows key pressed in output video

19 August 2013.

*stbt power* is a new command-line tool to switch on and off a
network-controllable power supply. See *stbt power --help* for details.
*stbt power* currently supports the following devices:

-   IP Power 9258, a family of devices sold under various brand names,
    for example [Aviosys](http://www.aviosys.com/9258st.html).
-   The KWX product line from
    [PDUeX](http://www.pdu-expert.eu/index.php/en/component/k2/itemlist/category/1).

*stbt control*, the interactive keyboard-based remote control input, can
now be used as input for *stbt record*. Use
*--control-recorder=stbt-control*. See the stbt(1) man page and *stbt
control --help* for details.

*stbt run* now passes excess command-line arguments on to the test
script. This allows you to run the same script with different arguments
when you need to run multiple permutations of a test case.

*stbt.press* now draws the name of the pressed key on the output video.
This makes it a lot easier to understand what is happening when watching
a test run, and more importantly, when triaging a failed test from its
recorded video.

The *restart_source* behaviour of *stbt run* and *stbt record* now
works correctly with the Hauppauge HDPVR video-capture device. (This was
broken since 0.14.)

Minor user-visible fixes:

-   *stbt.frames()* doesn't deadlock if called again when the iterator
    returned from a previous call is still alive.
-   *stbt run* and *stbt record* now honour *global.verbose* in the
    configuration file.
-   *stbt run* standard output includes the exception typename when a
    test script fails due to an unhandled exception.
-   *stbt record* fails immediately if no video is available (instead
    of failing after the second keypress of input).
-   *stbt control* now allows mapping the Escape key to a
    remote-control button.
-   *stbt control* displays a readable error message when the terminal
    is too small.
-   *stbt control* doesn't fail when you send keypresses too quickly.
-   *stbt tv* works correctly in a VirtualBox VM.
-   *stbt screenshot* takes an optional *filename* argument
    (overriding the default of *screenshot.png*).
-   *stbt screenshot* and *stbt templatematch* don't save a video if
    *run.save_video* is set in the user's configuration file.

Additionally, the following scripts are available from the source
repository:

-   [extra/vm](https://github.com/stb-tester/stb-tester/tree/master/extra/vm)
    contains scripts to set up a virtual machine with Ubuntu and
    stb-tester installed. These scripts use
    [vagrant](http://www.vagrantup.com), a tool for automatically
    provisioning virtual machines. See
    [extra/vm/README.rst](https://github.com/stb-tester/stb-tester/blob/master/extra/vm/README.rst)
    for instructions.
-   [extra/runner](https://github.com/stb-tester/stb-tester/tree/master/extra/runner)
    contains scripts that will run a set of stb-tester test scripts
    and generate an html report. See ["extra/runner: Bulk test running
    & reporting"](http://stb-tester.com/runner.html).

#### 0.14

Arbitrary image processing in user scripts; *stbt control*; *--save-video*;
miscellaneous improvements

9 July 2013.

*stbt.frames* allows a user's script to iterate over raw video frames in
the OpenCV format (i.e. a numpy array). This allows a user's script to
perform arbitrary image processing using the OpenCV python bindings. For
an example see the self-test
["test_using_frames_to_measure_black_screen"](https://github.com/stb-tester/stb-tester/blob/0.14/tests/test-stbt-py.sh#L96).
Note that *detect_match*, *wait_for_match*, *detect_motion*, etc.
are now implemented on top of *frames*. *get_frame* and *save_frame*
also return/operate on the OpenCV format.

*stbt control* is a new command-line tool to send remote control
commands programmatically (from a script) or interactively (with the PC
keyboard). The interactive mode requires a keymap file specifying the
keyboard keys that correspond to each remote-control button. See *stbt
control --help* for details.

*stbt run* accepts *--save-video* on the command line (or *[run]
save_video* in the config file) to record a video to disk. The video's
format is WebM, which is playable in web browsers that support the HTML5
video standard.

*stbt run* has always restarted the GStreamer source pipeline when video
loss is detected, to work around the behaviour of the Hauppauge HD PVR
video-capture device. Now this behaviour is configurable; if you use the
Hauppauge HD PVR you should set *restart_source = True* in the
*[global]* section of your stbt config file.

Minor user-visible fixes:

-   The default value for *wait_for_motion* *consecutive_frames*
    has changed from *10* to *"10/20"*, as promised in the 0.12
    release notes. This shouldn't affect most users.

-   The *wait_for_motion* visualisation has improved: It now
    highlights in red the parts of the screen where motion was
    detected, instead of flashing the entire screen red when motion
    was detected.

-   *wait_for_match* (and *detect_match*, *wait_for_motion*,
    etc.) raise *stbt.NoVideo* instead of *stbt.MatchTimeout* (etc.)
    when there is no video available from the video-capture device.

-   The GLib main loop, and the source-restarting functionality,
    operate continuously, not just inside *wait_for_match* (etc).
    User scripts that expect momentary video loss (e.g. scripts that
    reboot the device-under-test) can now be written as:

        wait_for_match("splash.png", timeout_secs=30)

    instead of:

        time.sleep(30)
        wait_for_match("splash.png")

-   *stbt record* now has the same recover-from-video-loss capability
    that *stbt run* has.

-   *stbt.get_config* works from scripts run with *python* (not just
    from scripts run with *stbt run*).

-   *stbt.get_config* accepts an optional *default* parameter, to
    return the specified default value instead of raising
    *ConfigurationError* if the specified *section* or *key* are not
    found in the config file.

Major changes under the covers (not visible to end users):

-   The image processing algorithms are implemented in *stbt.py* using
    the OpenCV python bindings. Performance isn't significantly
    affected. This simplifies the code substantially; the
    *stbt-templatematch* and *stbt-motiondetect* GStreamer elements
    are no longer necessary.

-   *make check* runs the self-tests in parallel if you have GNU
    *parallel* installed (On Fedora: yum install parallel).

#### 0.13

Image-matching algorithm is more configurable; changes to configuration API

21 May 2013.

Various parameters that affect the image-matching algorithm were
previously hard-coded but are now configurable by the user. You can
customise these parameters in individual calls to *wait_for_match*,
*detect_match*, and *press_for_match*, or you can change the global
defaults in your *stbt.conf* file. A new variant of the algorithm
(*confirm_method="normed-absdiff"*) has also been added, though the
default algorithm remains unchanged. For details see the documentation
for *MatchParameters* in the ["test script
format"](http://stb-tester.com/stbt.html#test-script-format) section of
the stbt(1) man page. See also
<http://stb-tester.com/match-parameters.html>

The *noise_threshold* parameter to *wait_for_match*, *detect_match*,
and *press_for_match* is now deprecated. It will be removed in a
future release. Set the *confirm_threshold* field of
*match_parameters* instead.

*stbt run* and *stbt record* now support multiple LIRC-based USB
infra-red emitters and/or receivers. For details see
<http://stb-tester.com/multi-lirc.html>

Breaking change to the *stbt.conf* configuration file: If you have any
of the following entries in the *[run]* or *[record]* section, move them
to the *[global]* section:

-   control
-   source_pipeline
-   sink_pipeline
-   verbose

If you have the following entry in the *[global]* section, move it to
the *[run]* section:

-   script

If you have the following entries in the *[global]* section, move them
to the *[record]* section:

-   output_file
-   control_recorder

This change is unlikely to affect most users; it will only affect you if
you changed the above configuration entries from their default sections.
See commit [9283df1f] for the rationale of this change.

Breaking API change to the python *stbt.get_config* function: The
function signature has changed from:

    stbt.get_config(key, section="global")

to:

    stbt.get_config(section, key)

This will only affect users who have written python libraries or
command-line tools that use *stbt.get_config* to access the *stbt.conf*
configuration file. See commit [e87299a1] for details.

Breaking change to the *stbt config* command-line tool: The command-line
interface has changed from:

    stbt config [section] key

to:

    stbt config section.key

This will only affect users who have written command-line tools that use
*stbt config* to access the *stbt.conf* configuration file. See commit
[f1670cbc] for details.

#### 0.12

New command-line tools; new *stbt.get_config* function; *wait_for_motion*
non-consecutive frames

14 March 2013.

New command-line tools:

-   stbt config: Print configuration value.
-   stbt screenshot: Capture a single screenshot.
-   stbt templatematch: Compare two images.
-   stbt tv: View live video on screen.

Use *stbt \<command\> --help* for usage details, and see the git commit
messages (e.g. *git log stbt-screenshot*) for the motivations behind
each tool.

New python function *stbt.get_config* for stbt scripts to read from the
stbt configuration file, using the search path documented in the
"configuration" section of the stbt(1) man page.

To avoid false positives, *wait_for_motion* looks for
*consecutive_frames* (10, by default) consecutive frames with motion.
However, this can give false negatives, so the *consecutive_frames*
parameter can now take a fraction given as a string, e.g. "10/20" looks
for at least 10 frames with motion out of a sliding window of 20. In a
future release we will probably make "10/20" the default.

#### 0.11

Support for RedRat irNetBox-II; improved robustness after video loss; improved
exception output

27 February 2013.

The RedRat irNetBox is a rack-mountable network-controlled infrared
emitter. This release adds support for the irNetBox model II; previously
only model III was supported. Thanks to Emmett Kelly for the patch.

The first *wait_for_match* after restarting pipeline (due to video
loss) now obeys *timeout_secs*. Due to a bug, the total timeout in this
situation used to be the specified *timeout_secs* plus the time the
script had spent running so far (possibly many minutes!). See commit
[cf57a4c2] for details.

Fixed bug observed with Blackmagic Intensity Pro video capture cards,
where restarting the pipeline (after momentary video loss) caused the
card to stop delivering timestamps in the video frames, causing *stbt
run* to hang. See commit [53d5ecf3] for details.

*stbt run* now prints an exception's name & message, not just the stack
trace. Since version 0.10, *stbt* wasn't printing this information for
non-*MatchTimeout* exceptions.

#### 0.10.1

Fix irNetBox connection retry

14 February 2013.

Release 0.10 was supposed to fix the irNetBox connection retry on Linux,
but in fact broke it for everyone. This release fixes that, and also
adds static analysis to "make check" so that this type of error doesn't
happen again.

#### 0.10

Fix irNetBox connection retry on Linux; other minor fixes

11 February 2013.

The irNetBox device only allows one TCP connection at a time, so when
multiple stbt tests are using the same irNetBox simultaneously, clashes
are inevitable. *stbt run* was supposed to retry refused connections,
but this was not working on Linux due to non-portable assumptions about
error numbers.

*stbt run* now saves a screenshot to disk for any exception with a
*screenshot* attribute, not just *stbt.MatchTimeout*.

The script generated by *stbt record* qualifies commands with *stbt.*
module, just to nudge people towards this best practice. In future we
might stop *stbt run* from implicitly importing *wait_for_match* etc.
into the top-level namespace, but for now the only change is to what
*stbt record* produces.

Other minor fixes:

-   Better build system error messages.
-   Minor fixes to the bash tab-completion script.

#### 0.9

Support for RedRat irNetBox; *wait_for_motion* more tolerant to noise

7 January 2013.

The [RedRat
irNetBox-III](http://www.redrat.co.uk/products/irnetbox.html) is a
rack-mountable network-controlled infrared emitter with 16 separate
outputs and adjustable power levels to avoid infrared interference
between the systems-under-test. For further information see the
*--control=irnetbox* configuration in the [stbt man
page](http://stb-tester.com/stbt.html#global-options), and commit
messages [508941e] and [778d847]. Many
thanks to Chris Dodge at RedRat for the donation of irNetBox hardware to
the stb-tester project and of his time in answering questions.

*wait_for_motion* now takes a
[noise_threshold](http://stb-tester.com/stbt.html#wait_for_motion)
parameter; decrease *noise_threshold* to avoid false positives when
dealing with noisy analogue video sources. Thanks to Emmett Kelly for
the patch!

Other minor changes:

-   The remote control implementations of *stbt.press* (Lirc,
    VirtualRemote, irNetBox) try to re-connect if the connection (to
    lircd, to the set-top box, to the irNetBox, respectively) had been
    dropped.

-   Build/packaging fix: Always rebuild *stbt* (which reports the
    version with *stbt --version*) when the version changes.

-   Minor fixes to the tab-completion script, self-tests and
    documentation.

#### 0.8

Bugfixes; *wait_for_match* returns the *MatchResult*; adds *get_frame*,
*save_frame*, *debug*

21 November 2012.

*wait_for_match* and *press_until_match* now return the
*MatchResult* object for successful matches, and *wait_for_motion*
returns the *MotionResult*. See commit [540476ff] for details.

New functions *get_frame* and *save_frame* allow capturing screenshots
at arbitrary points in the user's script. New function *debug* allows
user's scripts to print output only when stbt run "--verbose" was given.
Also documented the (existing) exception hierarchy in the README /
man-page.

Bugfixes:

-   Fixes a deadlock (introduced in 0.7) after GStreamer errors or
    video loss from the device under test.
-   Improves GStreamer pipeline restarting after transient video loss
    (see commit [2c434b2d] for details).
-   Fixes segfault in *stbt-motiondetect* GStreamer element when
    *debugDirectory* enabled with no mask.

Other minor changes:

-   The selftests now work correctly on OS X.
-   *make install* will rebuild *stbt* if given a different *prefix*
    directory than the *prefix* given to *make stbt*.

#### 0.7

Exposes *detect_match* and *detect_motion*; removes *directory* argument,
changes image search path

21 October 2012.

New functions *detect_match* and *detect_motion* provide low-level
access to all the information provided by the *stbt-templatematch* and
*stbt-motiondetect* GStreamer elements for each frame of video
processed. To keep your test scripts readable, I recommend against using
*detect_match* and *detect_motion* directly; they are intended for you
to write helper functions that you can then use in your scripts. For an
example see *wait_for_match* and *wait_for_motion* in stbt.py: They
are now implemented in terms of *detect_match* and *detect_motion*.

*wait_for_match*, *press_until_match* and *wait_for_motion* no
longer accept the optional *directory* argument. In most cases the
correct upgrade path is simply to not give the *directory* argument from
your scripts. These functions (plus *detect_match* and
*detect_motion*) now search for specified template or mask images by
looking in their caller's directory, then their caller's caller's
directory, etc. (instead of looking only in their immediate caller's
directory, or the directory specified as an argument). This allows you
to write helper functions that take an image filename and then call
*wait_for_match*. See commit message [4e5cd23c] for details.

Bugfixes and minor changes:

-   *stbt run* no longer requires an X-Windows display (unless you're
    using an X-Windows sink in your pipeline).
-   wait_for_motion and detect_motion visualisation: Detected
    motion is highlighted in red in the output video, and masked-out
    portions of the frame are darkened.
-   Additional wait_for_motion logging with *stbt run -vv*.
-   wait_for_motion fails immediately if a mask is given but not
    found on the filesystem.
-   Send an end-of-stream event in the pipeline teardown; this avoids
    corrupted videos when using a source or sink pipeline that records
    video to disk.
-   Reset wait_for_match after it fails. (If the user's script
    caught the MatchTimeout exception and continued, the
    stbt-templatematch element used to remain active, consuming CPU
    and showing the search rectangle on the output video.) Same fix
    for wait_for_motion, detect_motion, etc.
-   *stbt record* now accepts *-v* (or *--verbose*) command-line
    option (*stbt run* already did).
-   *stbt run* throws exceptions for all error conditions (instead of
    exiting with *sys.exit(1)* in some cases).
-   *stbt run* exposes the following exceptions directly in the
    script's namespace (so the script can say *except MatchTimeout*
    instead of *import stbt; except stbt.MatchTimeout*): UITestError,
    UITestFailure, MatchTimeout, MotionTimeout, ConfigurationError.
-   All functions and classes exposed to user scripts are now fully
    documented in the man page.
-   Fixes to the self-tests: *test_record* wasn't reporting failures;
    *test_wait_for_match_nonexistent_{template,match}* were
    failing intermittently.
-   RPM spec file in extras/

#### 0.6

Improves templatematch, adds *--verbose* flag, *certainty* renamed to
*noise_threshold*

5 September 2012.

The templatematch algorithm is more precise (see commit [ee28b8e] for
details). Taking advantage of this, *wait_for_match* now waits by
default for only one match.

The optional parameter *certainty* of *wait_for_match* and
*press_until_match* has been removed. Since 0.4 it actually didn't
have any effect. It has been replaced with the parameter
*noise_threshold*, a floating-point value between 0 and 1 that defaults
to 0.16. Increase it to be more tolerant to noise (small differences
between the desired template and the source video frame).

Debug output is disabled by default; use *--verbose* or *-v* to enable.
Use *-v -v* (or *-vv*) to enable additional debug, including dumping of
intermediate images by the stbt-templatematch and stbt-motiondetect
GStreamer elements (this is extremely verbose, and isn't intended for
end users).

libgst-stb-tester.so's *stbt-templatematch* element can now be installed
alongside libgstopencv.so's *templatematch* element.

MatchTimeout is reported correctly if the GStreamer pipeline failed to
start due to a v4l2 error (even better would be to detect the v4l2 error
itself).

Limit the maximum attempts to restart the pipeline in case of underrun
(e.g. on loss of input video signal). Previously, *stbt run* attempted
to restart the pipeline infinitely.

Fix *make install* with Ubuntu's shell (dash).

Other non-user-visible and trivial changes since 0.5:

-   stbt-templatematch bus message's parameter *result* is renamed to
    *match* and is now a boolean.
-   *make check* returns the correct exit status for failing
    self-tests.
-   The bash-completion script completes the *--help* flag.
-   Fix "unknown property debugDirectory" warning from
    *stbt-templatematch* element.

#### 0.5

*make install* installs stbt{-run,-record,.py} into \$libexecdir

14 August 2012.

The only difference from 0.4 is this change to install locations, for
the benefit of packagers.

#### 0.4

Adds gstreamer plugin, improved templatematch, motion detection

14 August 2012.

New "libgst-stb-tester.so" gstreamer plugin with stbt-templatematch
(copied from gst-plugins-bad and improved) and stbt-motiondetect
elements.

stbt scripts can use "wait_for_motion" to assert that video is
playing. "wait_for_motion" takes an optional "mask" parameter (a
black-and-white image where white pixels indicate the regions to check
for motion).

The improved templatematch is more robust in the presence of noise, and
can detect small but significant changes against large template images.

Other changes since 0.3:

-   Bash-completion script for stbt.
-   stbt no longer reads configuration from \$PWD/stbt.conf.
-   extra/jenkins-stbt-run is a shell script that illustrates how to
    use Jenkins (a continuous-integration system with a web interface)
    to schedule stbt tests and report on their results. See commit
    message [d5e7983] for instructions.

#### 0.3

Fixes *stbt run* freezing on loss of input video.

24 July 2012.

You will still see the blue screen when input video cuts out, but now
*stbt run* should recover after 5 - 10 seconds and continue running the
test script.

Other changes since 0.2:

-   Fix VirtualRemote recorder.
-   Clearer error messages on VirtualRemote failure to connect.
-   Added *certainty* optional argument to *press_until_match*
    (*wait_for_match* already takes *certainty*).
-   *man stbt* documents the optional arguments to *wait_for_match*
    and *press_until_match*.

#### 0.2

Adds configurability, IR blaster support.

6 July 2012.

Major changes since 0.1.1:

-   The source & sink gstreamer pipelines, the input & output remote
    control, and the input & output script filename, are all
    configurable.
-   Support for LIRC-based infrared emitter & receiver hardware.
-   Handle gstreamer errors.
-   Automated self-tests.

#### 0.1.1

Initial internal release, with packaging fixes.

21 June 2012.

The difference from 0.1 is that *make install* now works correctly from
a dist tarball.

#### 0.1

Initial internal release.

21 June 2012.
