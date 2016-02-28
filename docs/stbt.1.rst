======
 stbt
======

--------------------------------------------------------------
Automated User Interface Testing for Set-Top Boxes & Smart TVs
--------------------------------------------------------------

:Copyright: Copyright (C) 2013-2016 Stb-tester.com Ltd,
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

  roku:<hostname>
    Controls Roku players using the Roku's HTTP control protocol. Stb-tester's
    standard key names (like "KEY_HOME") will be converted to the corresponding
    Roku key name, or you can use the Roku key names directly.

  samsung:<hostname>[:<port>]
    Can be used to control Samsung Smart TVs using the same TCP network
    protocol that their mobile phone app uses.  Tested against a Samsung
    UE32F5370 but will probably work with all recent Samsung Smart TVs.

  none
    Ignores key press commands.

  test
    Used by the selftests to change the input video stream. Only works with
    `--source-pipeline=videotestsrc`. A script like `press("18")` will change
    videotestsrc's pattern property (see `gst-inspect videotestsrc`).

  x11:[<display>][,<key_mapping_file>]
    Send keypresses to a given X display using the xtest extension. Can be used
    with GStreamer's ximagesrc for testing desktop applications, websites and
    set-top box software running on a PC.

    The (optional) key_mapping_file is used to translate between the stb-tester
    keynames that you use in your test-scripts and X keysyms that X understands.
    The file looks like::

        # This is a comment

        KEY_FASTFORWARD   parenright
        KEY_REWIND        parenleft

    The column on the left is the key name you'll be using in your test-cases,
    the column on the right is the X keysym that that key will be translated to.
    For a full list of X keysyms see
    http://www.cl.cam.ac.uk/~mgk25/ucs/keysyms.txt .

    stbt provides some sensible default mappings when there is an obvious match
    for our `standard key names<https://stb-tester.com/stb-tester-one/rev2015.1/getting-started#remote-control-key-names>`_.

    The x11 control requires that `xdotool` is installed.

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


TEST SCRIPT FORMAT
==================

The test scripts produced and run by **stbt record** and **stbt run**,
respectively, are actually python scripts, so you can use the full power of
python. Don't get too carried away, though; aim for simplicity, readability,
and maintainability.

See the Python API documentation at
http://stb-tester.com/stb-tester-one/rev2015.1/python-api


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
