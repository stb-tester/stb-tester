Getting started with stb-tester
===============================

The following instructions assume a basic knowledge of the Unix command line
and of your system's package manager, and that you have read
[Introducing stb-tester].

## Install stb-tester

### On Fedora

Stb-tester supports Fedora 19 and 20.

Pre-built packages are provided via Fedora's [Copr] build service.

* Add the appropriate Copr repository. For Fedora 20:

        sudo wget -O /etc/yum.repos.d/stb-tester.repo \
            https://copr.fedoraproject.org/coprs/stbt/stb-tester/repo/fedora-20-i386/

    or for Fedora 19:

        sudo wget -O /etc/yum.repos.d/stb-tester.repo \
            https://copr.fedoraproject.org/coprs/stbt/stb-tester/repo/fedora-19-i386/

* Install stb-tester:

        sudo yum install stb-tester

* When a new stb-tester version is released, run this to upgrade:

        sudo yum update stb-tester

### On Ubuntu

Stb-tester supports Ubuntu 13.10 and 14.04.

Pre-built packages are provided via an Ubuntu [Personal Package Archive (PPA)].

* Add the PPA:

        sudo apt-get install software-properties-common  # for "add-apt-repository"
        sudo add-apt-repository ppa:stb-tester/stb-tester
        sudo apt-get update

* Install stb-tester:

        sudo apt-get install stb-tester

* When a new stb-tester version is released, run this to upgrade:

        sudo apt-get update
        sudo apt-get upgrade stb-tester

### On Windows or Mac OS X

On OS X or Windows, your best option is to run stb-tester inside a Linux
Virtual Machine (VM). Check out the stb-tester source code from [github] and
follow the instructions under [extra/vm/].

### Upgrading from versions older than 0.19

See the upgrade instructions in the [stb-tester 0.19 release notes].

## Set up the stb-tester configuration file

Create the file **~/.config/stbt/stbt.conf** (where "~" means your home
directory) with this content:

    [global]
    source_pipeline = videotestsrc is-live=true
    sink_pipeline = xvimagesink sync=false
    control = test

    [record]
    control_recorder=file:///dev/stdin

This format is known as "ini-file" format. The first line starts a *section*
called "global". The next three lines specify *keys* in the "global" section.

* **global.source_pipeline** tells stb-tester how to capture video from the
    device under test,
* **global.sink_pipeline** specifies how to display that video while stb-tester
    is running, and
* **global.control** specifies how to control the device under test.

Keys in the "global" section apply to all (or most) of stb-tester's
command-line tools. The next section ("record") only applies to the
*stbt record* tool, which we'll see in a minute.

* **record.control_recorder** specifies how *stbt record* reads remote-control
  button presses to record a test script.

For help on these configuration settings, see ["Options" in the stbt(1) man page].
For now we have specified stb-tester's built-in *video test source* and the
corresponding *test* control, just so that you can follow the next few examples
without having to worry about the complexities of real video-capture hardware.
We'll get to real hardware soon.

## Record a test script

<figure>
  <img src="images/videotestsrc.png">
</figure>

Now let's run stb-tester to record a test script:

    stbt record

You should see a window with the test pattern shown at right.

**stbt** is stb-tester's command-line tool; I like to pronounce it "stibbit".
**stbt record** will start recording a test script that can be run later with
**stbt run**.

*stbt record* will listen for remote-control keypresses on the
*control_recorder* we configured (standard input, that is, the keyboard), and
it will forward those keypresses to the system under test using the *control*
we configured (stb-tester's built-in *test* control).

Now type `gamut` into the terminal (and press return) and notice that the video
pattern has changed. Now type `checkers-8` (return), then `snow` (return), then
finish with Control-D or Control-C.

## Edit the test script

*stbt record* has created **test.py** and three png **screenshots**. Use an
image editor to crop the first two screenshots to what you want your test
script to match. When capturing from a real set-top box, this is most likely to
be a GUI element like a button or a logo.

The third screenshot (if you typed *snow* into standard input as per the
instructions in the previous section) will be random noise so whatever area you
crop is unlikely to be found as an exact match when you re-run the test case;
delete this screenshot.

Edit the test script to:

    import stbt

    def test_that_the_video_pattern_changes():
        stbt.press('gamut')
        stbt.wait_for_match('0000-gamut-complete.png')
        stbt.press('checkers-8')
        stbt.wait_for_match('0001-checkers-8-complete.png')
        stbt.press('snow')
        stbt.wait_for_motion()

The test script is written in the Python programming language. You can use any
Python feature, including Python's standard libraries; you can also use
third-party Python libraries if you have them installed on your system.

Each test case is a Python function that starts with **test_**.

**stbt.press** takes a string that must be understood by the control specified
in the configuration file.

**stbt.wait_for_match** looks for the specified image in the source video
stream. The image can be specified as an absolute path, or a relative path from
the location of the test script. It will raise a *stbt.MatchTimeout* exception
if no match is found.

**stbt.wait_for_motion** looks for changes in consecutive frames of the source
video stream. It will raise a *stbt.MotionTimeout* exception if no motion is
detected.

The *stbt* Python API is documented under
["Test script format" in the stbt(1) man page].

Note that if you want your test script to be the slightest bit maintainable,
you should rename the screenshots to something that reflects their content.

Once you start writing more complex scripts and reusing elements from previous
scripts, you might find that *stbt record* is too tedious. We prefer to write
the test scripts manually, and capture screenshots using **stbt screenshot**.
Run `stbt screenshot --help` for details.

## Test the test script

Now use **stbt run** to try the test script we just recorded:

    stbt run --verbose test.py::test_that_the_video_pattern_changes

Check *stbt*'s exit status (type `echo $?`) for success or failure. Read our
[Unix Shell tutorial] if you aren't familiar with process exit statuses on
Unix.

## Test running & reporting

Let's pretend that the above test script is designed to reproduce an
intermittent defect, so we want to run it over and over again. **stbt batch**
is stb-tester's bulk test-runner and reporting system:

    mkdir results  # Make a directory where you want to store the test results
    cd results
    stbt batch run /path/to/test.py::test_that_the_video_pattern_changes

After the test has run a few times, press Control-C to stop it. Now open
*index.html* in your web browser. You should see a report somewhat like this:

![](images/runner-report.png)

Each row represents one test run. Clicking on a row will reveal the **test
artifacts**: Logs from *stbt* and from your python script, and a video
recording of the test run.

*stbt batch* can run more that one test script, and it can run the tests just
once, repeatedly until one of them fails, or in soak (forever, until you kill
it). Type `stbt batch run -h` for help.

Your test scripts can create additional artifacts (logs) just by writing to the
current working directory -- these will appear in the *stbt batch* html report.
You can also **add arbitrary columns** to the table of test runs (for example,
if your test script is measuring channel-change time you can log that data to a
column). And you can write **classify scripts** to automatically populate the
"failure reason" column for known failures, to save manual triaging effort. For
more details see [stbt batch: Stb-tester’s bulk test running & reporting tool].

## Use real hardware

The following diagram shows a setup that uses the Hauppauge HD PVR for video
capture, a USB infrared emitter for controlling the system under test, and
a USB infrared receiver for recording tests.

![](images/stb-tester-setup.svg)

### Real video source

Using video from a real device-under-test is simply a matter of replacing
stb-tester's *global.source_pipeline* configuration value. See
[Video-capture hardware for DIY stb-tester rigs] for the *source_pipeline*
configuration for various video-capture hardware.

Test your *source_pipeline* configuration by running `stbt tv`.

If you have trouble getting your video-capture hardware to work, read the
[Appendix: Gstreamer primer] below.

### Real control mechanism

Stb-tester supports various control mechanisms. Which one you choose depends on
the type of device you want to test.

**Infrared** remote control: Stb-tester supports [LIRC]-compatible USB
infra-red emitters, and the network-controlled [RedRat irNetBox]. For
configuration instructions see [Infrared hardware for DIY stb-tester rigs].

**Network-based** remote control: Some Smart TVs can be controlled over the
network. Currently stb-tester supports Samsung TVs; see the documentation for
["control" in the stbt(1) man page] for configuration details.

For other control methods, add your own receiver and emitter code and send us a
pull request on github.

## stbt control

**stbt control** is an interactive command-line tool for when you want to
manually control your device-under-test by using stb-tester's control hardware
instead of the remote control unit that shipped with your device-under-test.
Used in conjunction with **stbt tv** it allows you to manually interact with a
device that isn't necessarily on your desk or even in the same room.

You'll need to create a keymap file that maps from keys on your computer
keyboard to key names in your LIRC (or irNetBox, etc) configuration file. Run
`stbt control --help` for details (and run `stbt --help` to see what other
*stbt* commands are available).

You can also use *stbt control* as the *control recorder* for *stbt record*.
See the documentation for ["control" in the stbt(1) man page] for configuration
details.

## Multiple devices under test

Once you start working with multiple devices under test connected to a single
PC (each with its own video-capture and control hardware), you can keep a
separate configuration file for each device under test and set the environment
variable *STBT_CONFIG_FILE* to point to the appropriate configuration file
before running *stbt*. See our [Unix Shell tutorial] if you're not familiar
with environment variables.

## Get in touch

If you have found stb-tester useful, or just intriguing, or you have any
questions, let us know! You'll find us on the [mailing list](
http://groups.google.com/group/stb-tester).

## Appendix: GStreamer primer

Stb-tester is built on top of [GStreamer], a library of media-handling
components. GStreamer has two release series that are not compatible with each
other but that can both be installed at the same time: GStreamer 0.10 and
GStreamer 1.x[^package-names]. Stb-tester uses GStreamer 1.x.

Once you have installed stb-tester, you can verify that GStreamer is installed
correctly by running this:

    gst-launch-1.0 videotestsrc ! autovideosink

<figure>
  <img src="images/videotestsrc.png">
</figure>

You should see an X window with the test pattern shown at right.

**gst-launch-1.0** takes a GStreamer *pipeline* — the "**!**" is the GStreamer
equivalent of the Unix pipe "**|**". The **videotestsrc** element generates a
video stream; **autovideosink** displays it using the best sink available.

Instead of *autovideosink* you could choose a specific sink such as
**ximagesink** or **xvimagesink** to use the X-Windows or XVideo APIs,
respectively. Or **fakesink**, which is a null sink--but then you won't see
anything at all. Or **udpsink** to stream the video to a **udpsrc** on another
computer. Or **filesink** to save the raw data to disk.

GStreamer elements can be configured by setting their **properties**:

    gst-launch-1.0 videotestsrc pattern=snow ! autovideosink

Use **gst-inspect-1.0** to list an element's properties:

    gst-inspect-1.0 videotestsrc

Unlike *videotestsrc*, some source elements provide compressed video. For
example, the [Hauppauge HD PVR] produces an MPEG-TS container with
H.264-encoded video. So with the Hauppauge device we need the following
pipeline:

    gst-launch-1.0 v4l2src device=/dev/video0 ! tsdemux ! h264parse ! \
        decodebin ! videoconvert ! autovideosink

**v4l2src** is a source element that should work with any device with
Video-for-Linux drivers. **tsdemux** demultiplexes an MPEG-TS container into
its component programs (here we only care about the first --and only-- video
program). **h264parse** parses the stream and adds the extracted metadata
--needed by the downstream GStreamer elements-- to each frame. **decodebin**
picks the appropriate decoder and outputs raw video. **videoconvert** performs
colorspace conversion (for example from YUV to RGB) if the sink doesn't support
the colorspace from decodebin.

If you're using Fedora, you'll have to install the H.264 decoder manually
by installing **gstreamer1-libav** from the [RPM Fusion free] repository.
On Ubuntu this will have been installed already by the stb-tester package.

Stb-tester's **global.source_pipeline** configuration key takes a fragment of a
GStreamer pipeline -- everything up to (but not including) the *decodebin*.

Make sure you get your own video capture pipeline working with *gst-launch-1.0*
before attempting to use it with *stbt*. Debugging a GStreamer pipeline can be
difficult, so make sure that you understand all the GStreamer concepts we've
covered so far. Read the output from *gst-launch-1.0* carefully. If you get a
"not negotiated" error, check that each element's source capabilities[^caps]
match the sink capabilities of the element it's linked to. If there's an
incompatibility between raw video formats, use the *videoconvert* element to
convert. Try enabling debug logging[^gst-debug] for one element at a time (if
you enable debug for all elements at once, you'll be overwhelmed by thousands
of lines of output).


[^package-names]: On Fedora, for example, GStreamer 0.10 packages are called
    "gstreamer", "gstreamer-plugins-base", etc., while GStreamer 1.x packages
    are "gstreamer1", "gstreamer1-plugins-base", etc.

[^caps]: See ["Media Formats and Pad Capabilities"] in the GStreamer SDK
    tutorial.

[^gst-debug]: See ["Debugging tools"] in the GStreamer SDK tutorial.


[Introducing stb-tester]: http://stb-tester.com/introduction.html
[Copr]: https://copr.fedoraproject.org/coprs/stbt/stb-tester/
[Personal Package Archive (PPA)]: https://launchpad.net/~stb-tester/+archive/stb-tester
[stb-tester 0.19 release notes]: http://stb-tester.com/release-notes.html#0.19
[github]: https://github.com/drothlis/stb-tester
[extra/vm/]: https://github.com/drothlis/stb-tester/tree/master/extra/vm
["Options" in the stbt(1) man page]: http://stb-tester.com/stbt.html#options
["Test script format" in the stbt(1) man page]: stbt.html#test-script-format
[Unix Shell tutorial]: http://stb-tester.com/shell.html
[stbt batch: Stb-tester’s bulk test running & reporting tool]: http://stb-tester.com/runner.html
[Video-capture hardware for DIY stb-tester rigs]: http://stb-tester.com/video-capture.html
[Appendix: Gstreamer primer]: #appendix-gstreamer-primer
[LIRC]: http://www.lirc.org
[RedRat irNetBox]: http://www.redrat.co.uk/products/irnetbox.html
[Infrared hardware for DIY stb-tester rigs]: http://stb-tester.com/infrared.html
["control" in the stbt(1) man page]: http://stb-tester.com/stbt.html#global-options
[GStreamer]: http://gstreamer.freedesktop.org
[Hauppauge HD PVR]: http://www.hauppauge.com/site/products/data_hdpvr.html
[RPM Fusion free]: http://rpmfusion.org/Configuration
["Media Formats and Pad Capabilities"]: http://docs.gstreamer.com/display/GstSDK/Basic+tutorial+6%3A+Media+formats+and+Pad+Capabilities
["Debugging tools"]: http://docs.gstreamer.com/display/GstSDK/Basic+tutorial+11%3A+Debugging+tools
