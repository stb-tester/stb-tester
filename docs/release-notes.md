stb-tester release notes
========================

[stb-tester](http://stb-tester.com) python APIs for use in test scripts are
stable: If better APIs are introduced, the existing API will be marked as
deprecated but not removed for one year. Similarly, the command-line interfaces
of *stbt run*, *stbt record*, *stbt batch*, *stbt config*, *stbt control*,
*stbt power*, *stbt screenshot*, *stbt templatematch*, and *stbt tv* are
stable. Other command-line utilities are considered experimental, but we always
endeavour to keep backwards compatibility. The release notes always provide an
exhaustive list of any changes, along with upgrade instructions where
necessary.

For installation instructions see [Getting Started](
https://github.com/stb-tester/stb-tester/wiki/Getting-started-with-stb-tester).

#### 23

New `stbt batch run --shuffle` option to run test cases in a random order.

8 July 2015.

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

##### Developer-visible changes since 22

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

##### Developer-visible changes since 0.21

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
  [stbt(1) man page](http://stb-tester.com/stbt.html).

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

##### Developer-visible changes since 0.20

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

##### Developer-visible changes since 0.19 beta

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
    reboot the system-under-test) can now be written as:

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
    video loss from the system under test.
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
