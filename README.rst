======
 stbt
======

-----------------------------------------------------------------------------
A video-capture record/playback system for automated testing of set-top boxes
-----------------------------------------------------------------------------

:Copyright: Copyright (C) 2012 YouView TV Ltd.
:License: LGPL v2.1 or (at your option) any later version (see LICENSE file in
          the source distribution for details)
:Version: @VERSION@
:Manual section: 1
:Manual group: stb-tester

SYNOPSIS
========

stbt record [options]

stbt run [options] [script]


DESCRIPTION
===========

**stbt record** will record a test case by listening for remote-control
keypresses, taking screenshots from the set-top box as it goes.

You then (manually) crop the screenshots to the region of interest.

(Optionally) you manually edit the generated test script, which will look
something like this::

    press("MENU")
    wait_for_match("Guide.png")
    press("OK")
    wait_for_match("BBC One.png")

**stbt run** will play back the given test script, returning an exit status of
success or failure for easy integration with your existing test reporting
system.


OPTIONS
=======

Global options
--------------

--control=<uri>
  A remote control to use for controlling the set top box. `uri` can be:

  lirc:<lircd_socket>:<remote_control_name>
    A hardware infrared emitter controlled by the lirc (Linux Infrared Remote
    Control) daemon. `lircd_socket` defaults to `/var/run/lirc/lircd`.
    `remote_control_name` is the name of a remote-control specification in
    lircd.conf.

  vr:<hostname>:<port>
    A "virtual remote" that communicates with the set-top box over TCP.
    Requires a virtual remote listener (which we haven't released yet) running
    on the stb.

  none
    Ignores key press commands.

  test
    Used by the selftests to change the input video stream. Only works with
    `--source-pipeline=videotestsrc`. A script like `press("18")` will change
    videotestsrc's pattern property (see `gst-inspect videotestsrc`).

--source-pipeline=<pipeline>
  A gstreamer pipeline providing a video stream to use as video output from the
  set-top box under test.  For the Hauppauge HD PVR use::

      v4l2src device=/dev/video0 ! mpegtsdemux ! video/x-h264 ! decodebin2

--sink-pipeline=<pipeline>
  A gstreamer pipeline to use for video output, like `xvimagesink`.

Additional options to stbt record
---------------------------------

--control-recorder=<uri>
  The source of remote control presses.  `uri` can be:

  lirc:<lircd_socket>:<remote_control_name>
    A hardware infrared receiver controlled by the lirc (Linux Infrared Remote
    Control) daemon. `lircd_socket` and `remote_control_name` are as for
    `--control`.

  vr:<hostname>:<port>
    Listens on the socket <hostname>:<port> for a connection and reads a
    "virtual remote" stream (which we haven't documented yet, but we'll
    probably change it soon to be compatible with LIRC's protocol).

  file://<filename>
    Reads remote control keypresses from a newline-separated list of key names.
    For example, `file:///dev/stdin` to use the keyboard as the remote control
    input.

-o <filename>, --output-filename=<filename>
  The file to write the generated test script to.


CONFIGURATION
=============

All parameters that can be passed to the stbt tools can also be specified in
configuration files. Configuration is searched for in the following files (with
later files taking precedence):

1. /etc/stbt/stbt.conf
2. ~/.config/stbt/stbt.conf
3. $PWD/stbt.conf
4. $STBT_CONFIG_FILE

These files are simple ini files with the form::

    [global]
        source_pipeline=videotestsrc
        control=None
    [run]
        script=test.py
    [record]
        output_file=test.py
        control_recorder=file:///dev/stdin

Each key corresponds to a command line option with hyphens replaced with
underscores.  Configuration items in the 'global' section will be passed to
all tools; this can be overridden in the sections corresponding to each of the
individual tools.


HARDWARE REQUIREMENTS
=====================

The test rig consists of a Linux server, with:

* A video-capture card (for capturing the output from the system under test)
* An infrared receiver (for recording test cases)
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

stb-tester uses gstreamer, an open source multimedia framework. Instead of a
video-capture card you can use any gstreamer video-source element. For example:

* If you run tests against a VM running the set-top box software instead
  of a physical set-top box, you could use the ximagesrc gstreamer
  element to capture video from the VM's X Window.

* If your set-top box uses DirectFB, you could install the (not yet written)
  DirectFBSource gstreamer element on the set-top box to stream video to a
  tcpclientsrc or tcpserversrc gstreamer element on the test rig.

Instead of a hardware infra-red receiver + emitter, you can use a software
equivalent (for example a server running on the set-top box that listens on
a TCP socket instead of listening for infra-red signals, and your own
application for emulating remote-control keypresses). Using a software remote
control avoids all issues of IR interference in rigs testing multiple set-top
boxes at once.

Linux server
------------

We expect that an 8-core machine will be able to drive 4 set-top boxes
simultaneously with at least 1 frame per second per set-top box.
(TODO: Assuming enough bandwidth on the USB bus -- need to test this).


SOFTWARE REQUIREMENTS
=====================

* A Unixy operating system (we have only tested on Linux; gstreamer and OpenCV
  allegedly work on BSD, Mac OS X, and possibly Windows with MingW/MSys; but
  building gst-plugins-bad, below, can be tricky).

* Drivers for any required hardware components

* gstreamer 0.10 (multimedia framework) + gst-plugins-base + gst-plugins-good.

* python (we have tested with 2.6 and 2.7) + pygst + pygtk2 (+ nose for the
  self-tests).

* OpenCV (image processing library) version >= 2.0.0 and <= 2.3.1
  (the version restrictions are imposed by gst-plugins-bad).

* gst-plugins-bad (for the gstreamer wrappers around OpenCV)
  built from source from the head of the 0.10 branch, with the patches from
  https://bugzilla.gnome.org/show_bug.cgi?id=678485
  (until such time as the patches are accepted upstream).

  A github repo with the same patches applied is available at
  https://github.com/drothlis/gst-plugins-bad (branch templatematch-fixes).

* For the Hauppauge video capture device you'll need the gstreamer-ffmpeg
  package (e.g. from the rpmfusion-free repository) for H.264 decoding.


INSTALLING FROM SOURCE
======================

Run "make install" from the stb-tester source directory.

Requires python-docutils (for building the documentation).


SETUP TIPS
==========

Use "gst-inspect templatematch" to check that gstreamer can find the
templatematch element. You may need to set GST_PLUGIN_PATH to point
where you installed gst-plugins-bad.

Run tests/run-tests.sh to verify that your gstreamer + OpenCV installation is
working correctly.

If you plan to use real infrared emitters/receivers, use lirc's irsend(1) and
ircat(1), respectively, to test your lirc setup before integrating with
stb-tester.


TEST SCRIPT FORMAT
==================

The test scripts produced and run by **stbt record** and **stbt run**,
respectively, are actually python scripts, so you can use the full power of
python. Don't get too carried away, though; aim for simplicity, readability,
and maintainability.

The following functions are available (the "keyword arguments" like
`timeout_secs` are optional, and default to the value shown)::

  press("KEY NAME")

  wait_for_match("filename.png", timeout_secs=10, certainty=0.99)

  press_until_match("KEY NAME", "filename.png",
                    interval_secs=3, max_presses=10, certainty=0.99)


TEST SCRIPT BEST PRACTICES
==========================

* When cropping images to be matched by a test case, you must select a region
  that will *not* be present when the test case fails, and that does *not*
  contain *any* elements that might be absent when the test case succeeds. For
  example, you must not include any part of a live TV stream (which will be
  different each time the test case is run), nor translucent menu overlays with
  live TV showing through.

* Don't crop tiny images: Instead of selecting just the text in a menu button,
  select the whole button. (Larger images provide a greater gap between the
  "match certainty" reported for non-matching vs. matching images, which makes
  for more robust tests).


SEE ALSO
========

* http://stb-tester.com/
* http://github.com/drothlis/stb-tester


AUTHORS
=======

* Will Manley <will@williammanley.net>
* David Rothlisberger <david@rothlis.net>
