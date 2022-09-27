# Automated tests to verify your gstreamer installation.
# Run with ./run-tests.sh

# Test for a correct installation of gstreamer
test_gstreamer_core_elements() {
    $timeout 10 gst-launch-1.0 videotestsrc num-buffers=10 ! fakesink
}
