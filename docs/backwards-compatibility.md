# Backwards compatibility notes

## 0.18 -> 0.19

### Porting from GStreamer 0.10 to GStreamer 1.0

In 0.19 we migrated stb-tester from GStreamer 0.10 to 1.0.  This should require
**no changes to test scripts** but **configuration may need to be updated**.
It is also no longer required that source pipelines output raw video.
stb-tester may even be able to save memory if it is fed compressed video.

Specifically you may need to update `global.source_pipeline` in your
`stbt.conf`.  Some GStreamer elements have been renamed:

stb-tester 0.18    | stb-tester 0.19
------------------ | ---------------
`ffmpegcolorspace` | `videoconvert`
`decodebin2`       | `decodebin`
`mpegtsdemux`      | `tsdemux`

For more information see section '"soft" API changes' in the [GStreamer 0.10 to
1.0 porting guide][gstport].

Advice for users of specific hardware:

*   **Hauppauge HD-PVR**.  `source_pipeline` should become:

        v4l2src device=/dev/video0 ! tsdemux ! h264parse

    Note: to use the HD-PVR with GStreamer 1.0 you need to have
    gst-plugins-good version >=1.2.4 or an earlier version with the patches
    from GStreamer bugzilla [#725860] applied.

*   **Teradek VidiU** - `source_pipeline` should become:

        rtmpsrc location=rtmp://localhost/live/stream-name\ live=1

    Note: With GStreamer 1.0 there is a 20s delay during VidiU pipeline
    shutdown.  This shouldn't affect your ability to test with the VidiU but we
    are looking into it.

*   **Blackmagic Intensity Pro** - In GStreamer 1.0 `decklinksrc`'s `subdevice`
    property has been renamed to `device-number`. You also need to add a
    `videoconvert` element. So `source_pipeline` should become:

        decklinksrc mode=... connection=... device-number=0 ! videoconvert

    (Where `mode` and `connection` should be set to the appropriate values for
    your hardware setup; these values haven't changed since GStreamer 0.10.)

[gstport]: http://cgit.freedesktop.org/gstreamer/gstreamer/tree/docs/random/porting-to-1.0.txt
[#725860]: https://bugzilla.gnome.org/show_bug.cgi?id=725860
