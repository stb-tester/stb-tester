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

stbt run [options] script[::testcase]


DESCRIPTION
===========

**stbt run** will run the given testcase, using the live video-stream captured
from the device-under-test as input, and a remote control (usually an infrared
transmitter) to control the device-under-test.

Testcases are written in the Python programming language. They look like this::

    def test_that_i_can_tune_to_bbc_one_from_the_guide():
        stbt.press("KEY_EPG")
        stbt.wait_for_match("Guide.png")
        stbt.press("KEY_OK")
        stbt.wait_for_match("BBC One.png")

``stbt`` has other commands apart from ``run``; see ``stbt --help`` for
details.


OPTIONS
=======

Global options
--------------

--control=<uri>
  A remote control to use for controlling the set top box. `uri` can be:

  adb[:address]
    Uses ADB (Android Debug Bridge) to control an Android TV or Amazon Fire TV
    device. You will need to enable "ADB Debugging" on the Android device.
    `address` is the IP address of the Android device, or the serial number of
    an Android device connected by USB. If `address` is not specified, there
    must be only one Android device connected by USB.

  error[:message]
    Raises `RuntimeError` when the test script calls `stbt.press`, with the
    optional error message.

  file[:<filename>]
    Append a newline seperated key name to the given file for each press.
    Mostly useful for testing stb-tester itself. If a filename is not specified
    it defaults to stdout.

  hdmi-cec[:<device>[:<source>[:<destination>]]]
    In conjuction with a USB-CEC adaptor this controls a set-top box by sending
    key-presses over HDMI.  This is useful for devices that lack an IR input
    such as the Playstation 4.

    * device - The USB-CEC adaptor to use. Leave empty to auto-detect.

    * source/destination - A hexidecimal number between 0 and f indicating the
      HDMI source/destination. Source defaults to 1 (Recording 1). Destination
      defaults to the last device present on the CEC bus.

        * 0 - TV
        * 1 - Recording 1
        * 2 - Recording 2
        * 3 - Tuner 1
        * 4 - Playback 1
        * 5 - Audio system
        * 6 - Tuner 2
        * 7 - Tuner 3
        * 8 - Playback 2
        * 9 - Playback 3
        * a - Tuner 4
        * b - Playback 3
        * c - Reserved
        * d - Reserved
        * e - Reserved
        * f - Unregistered (source)/Broadcast (destination)

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

  none
    Ignores key press commands.

  rfb:<hostname>[:<port>]
    Use the VNC RFB protocol (RFC6143). This is used by Cisco to control some
    of their set-top boxes. Traditionally the RFB protocol uses key codes that
    are the same as used by X, but this control implements Cisco-specific
    keycodes.

  roku:<hostname>
    Controls Roku players using the Roku's HTTP control protocol. Stb-tester's
    standard key names (like "KEY_HOME") will be converted to the corresponding
    Roku key name, or you can use the Roku key names directly.

  samsung:<hostname>[:<port>]
    Can be used to control Samsung Smart TVs using the same TCP network
    protocol that their mobile phone app uses.  Tested against a Samsung
    UE32F5370 but will probably work with all recent Samsung Smart TVs.

  test
    Used by stb-tester's self-tests to change the input video stream. Only
    works with `--source-pipeline=videotestsrc`. A script like `press("snow")`
    will change videotestsrc's pattern property (see `gst-inspect
    videotestsrc`).

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
    for our `standard key names <https://stb-tester.com/manual/getting-started#remote-control-key-names>`_.

    The x11 control requires that `xdotool` is installed.

--source-pipeline=<pipeline>
  A GStreamer pipeline providing a video stream to use as video output from the
  set-top box under test.  For the Hauppauge HD PVR use::

      v4l2src device=/dev/video0 ! tsdemux ! h264parse

--sink-pipeline=<pipeline>
  A GStreamer pipeline to use for video output, like `xvimagesink`.

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


CONFIGURATION
=============

All parameters that can be passed to the stbt tools can also be specified in
configuration files. Configuration is searched for in the following files (with
earlier files taking precedence):

1. $STBT_CONFIG_FILE
2. ~/.config/stbt/stbt.conf
3. /etc/stbt/stbt.conf

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

Each key corresponds to a command line option with hyphens replaced with
underscores.


EXIT STATUS
===========

**stbt run** returns 0 on success; 1 on test script failure; 2 on any other
error.

Test scripts indicate **failure** (the device under test didn't behave as
expected) by raising an instance of `stbt.UITestFailure` (or a subclass
thereof) or `AssertionError` (which is raised by Python's `assert` statement).
Any other exception is considered a test **error** (a logic error in the test
script, an error in the device under test's environment, or an error in the
test framework itself).


HARDWARE REQUIREMENTS
=====================

Use the **stb-tester ONE** (sold by Stb-tester.com Ltd., the maintainers of the
stb-tester project; see https://stb-tester.com) or see the stb-tester wiki for
consumer video-capture & infrared hardware if you want to build your own rig:
https://github.com/stb-tester/stb-tester/wiki


TEST SCRIPT FORMAT
==================

Testcases are written in Python, using the ``stbt`` API documented at
https://stb-tester.com/manual/python-api


SEE ALSO
========

* https://stb-tester.com/
* https://github.com/stb-tester/stb-tester
