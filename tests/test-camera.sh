# Run with ./run-tests.sh

skip_if_no_rsvg_plugins() {
    if ! gst-inspect-1.0 rsvg 2>&1 >/dev/null; then
        skip "rsvg GStreamer plugins not installed"
    fi
}
skip_if_no_stbt_camera() {
    if ! stbt --with-experimental camera -h &>/dev/null; then
        skip "stbt camera is not installed"
    fi
}
skip_if_no_stbt_plugins() {
    if ! gst-inspect-1.0 stbt &>/dev/null; then
        skip "stbt GStreamer plugins not installed"
    fi
}

stb_tester_logo_src_1080p="\
    videotestsrc pattern=solid-color \
    ! video/x-raw,width=1280,height=720 \
    ! rsvgoverlay location=$testdir/stb-tester-350px.svg x=465 y=210 \
    ! videoscale \
    ! video/x-raw,width=1920,height=1080 \
    ! videoconvert "

###
### stbtgeometriccorrection tests
###

create_stb_tester_logo_template() {
    # Can't just use rsvgdec as it doesn't seem to respect the white background
    # colour in the svg
    gst-launch-1.0 videotestsrc pattern=solid-color \
                 ! video/x-raw,width=349,height=301 \
                 ! rsvgoverlay location="$testdir/stb-tester-350px.svg" \
                 ! videoconvert ! video/x-raw,format=RGB ! pngenc snapshot = true \
                 ! filesink location="stb-tester-350px.png"
}

test_that_stbtgeometriccorrection_scales_by_default() {
    skip_if_no_stbt_plugins
    skip_if_no_rsvg_plugins

    start_fake_video_src_launch_1080 $stb_tester_logo_src_1080p &&
    set_config global.transformation_pipeline "stbtgeometriccorrection" &&
    set_config global.control "none" &&

    create_stb_tester_logo_template &&
    echo 'wait_for_match("stb-tester-350px.png")' >test.py &&
    stbt run -v test.py
}

# Properties to be passed to stbtgeometriccorrection to flatten capture-logo.png.
# capture-logo.png was taken with a Logitech C920 webcam.
wp_matricies='
    camera-matrix="1491.1536435672558    0.0             929.63729425798135
                      0.0             1490.0565740887305 569.55885903330557
                      0.0                0.0               1.0"

    distortion-coefficients="0.12152211775145583 -0.28102519335279752
        0.00020128754517049412 3.738779032027093e-05 0.08124443207970744"

    inv-homography-matrix="0.00078482598991913902 -3.0756177190069151e-05 -0.48720520841063641
                           3.731138534585565e-05   0.00078626284743211832 -0.33698755050692453
                          -7.8645779307294576e-05  6.6181312307411495e-05  1.0236834039817024"'
wp_props="$(echo "$wp_matricies" | tr '\n' ' ')"

test_that_stbtgeometriccorrection_flattens_pictures_of_TVs() {
    skip_if_no_stbt_plugins
    skip_if_no_rsvg_plugins

    create_stb_tester_logo_template &&
    start_fake_video_src_launch_1080 uridecodebin "uri=file://$testdir/capture-logo.png" ! videoconvert ! imagefreeze &&
    set_config global.transformation_pipeline "stbtgeometriccorrection $wp_props" &&
    set_config global.control "none" &&

    create_stb_tester_logo_template &&
    echo 'wait_for_match("stb-tester-350px.png",
                         match_parameters=MatchParameters(confirm_threshold=0.3))' >test.py &&
    stbt run -v test.py
}

test_that_stbt_camera_calibrate_corrects_for_geometric_distortion() {
    skip_if_no_stbt_camera
    skip_if_no_rsvg_plugins

    set_config camera.tv_driver assume
    set_config global.control none

    start_fake_video_src_launch_1080 \
        uridecodebin "uri=file://$testdir/capture-chessboard.png" \
        ! videoconvert ! imagefreeze &&

    stbt --with-experimental camera calibrate --noninteractive --skip-illumination &&
    start_fake_video_src_launch_1080 \
        uridecodebin "uri=file://$testdir/capture-letters-bw.png" \
        ! videoconvert ! imagefreeze &&
    stbt --with-experimental camera validate --positions-only letters-bw
}

###
### Fake Video Source - test infrastructure.
###

fake_video_src_source="\
    shmsrc do-timestamp=true is-live=true blocksize=2764800 \
    socket-path=gst-shm-socket ! \
    video/x-raw,format=RGB,width=1280,height=720,framerate=25/1 ! queue ! \
    videoconvert"

start_fake_video_src() {
    if [ -n "$FAKE_VIDEO_SRC_PID" ]; then
        echo "Restarting Fake video src"
        stop_fake_video_src
    else
        echo "Starting Fake video src"
    fi

    rm -f gst-shm-socket
    mkfifo uri_playlist
    while cat uri_playlist; do true; done | \
        PYTHONPATH=$testdir/..:$PYTHONPATH "$testdir/fake-video-src.py" "$PWD/gst-shm-socket" &
    FAKE_VIDEO_SRC_PID=$!
    trap stop_fake_video_src EXIT
    while [ ! -e gst-shm-socket ]; do
        sleep 0.1
    done
    if [ -n "$1" ]; then
        overlay="rsvgoverlay location=$1"
    else
        overlay="identity"
    fi

    set_config global.source_pipeline "shmsrc \
        do-timestamp=true is-live=true blocksize=2764800 \
        socket-path=$PWD/gst-shm-socket ! \
        video/x-raw,format=RGB,width=1280,height=720,framerate=25/1 ! \
        videoconvert ! $overlay ! videoscale ! videoconvert ! \
        video/x-raw,format=RGB,width=1920,height=1080"

    set_config camera.tv_driver fake:uri_playlist
}

start_fake_video_src_launch()
{
    frame_bytes="$(expr $WIDTH \* $HEIGHT \* 3)"
    shm_size="$(expr $frame_bytes \* 1000)"
    rm -f gst-shm-socket
    gst-launch-1.0 "$@" \
        ! video/x-raw,format=RGB,width=$WIDTH,height=$HEIGHT,framerate=25/1 \
        ! queue ! shmsink "wait-for-connection=true" "shm-size=$shm_size" \
          socket-path=$PWD/gst-shm-socket blocksize=$frame_bytes sync=true \
          buffer-time=100000000 &
    FAKE_VIDEO_SRC_PID=$!
    trap stop_fake_video_src EXIT
    while [ ! -e gst-shm-socket ]; do
        sleep 0.1
    done

    set_config global.source_pipeline \
        "shmsrc do-timestamp=true is-live=true blocksize=$frame_bytes \
        socket-path=$PWD/gst-shm-socket ! \
        video/x-raw,format=RGB,width=$WIDTH,height=$HEIGHT,framerate=25/1"
}

start_fake_video_src_launch_720()
{
    WIDTH=1280
    HEIGHT=720
    start_fake_video_src_launch "$@"
}

start_fake_video_src_launch_1080()
{
    WIDTH=1920
    HEIGHT=1080
    start_fake_video_src_launch "$@"
}

fake_video_src_show() {
    echo "$1" >uri_playlist
}

stop_fake_video_src() {
    kill "$FAKE_VIDEO_SRC_PID"
    unset FAKE_VIDEO_SRC_PID
    rm -f uri_playlist gst-shm-socket
    true
}

###
### stbt camera validate tests
###

run_validation() {
    color="$1"
    extra=${2:-identity}

    skip_if_no_stbt_camera
    skip_if_no_rsvg_plugins

    start_fake_video_src_launch_720 filesrc location="$testdir/$color.png" ! pngdec \
        ! videoconvert ! $extra ! videoconvert \
        ! video/x-raw,width=1280,height=720 ! imagefreeze &&
    set_config global.control none &&
    stbt --with-experimental camera validate --tv-driver=assume "$color"
}

test_that_validation_passes_on_pristine_input() {
    run_validation letters-bw || fail "Validation failed on pristine input"
}
test_that_validation_fails_if_letters_are_offset() {
    run_validation letters-bw "videobox top=-2 left=-2 ! \
                       videobox autocrop=true" \
        && fail "Validation succeeded on invalid input"
    return 0
}
test_that_validation_fails_if_letters_are_scaled_down() {
    run_validation letters-bw "videoscale ! video/x-raw,width=1278,height=718 ! \
                       videobox autocrop=true" \
        && fail "Validation succeeded on invalid input"
    return 0
}
test_that_validation_fails_if_letters_are_scaled_up() {
    run_validation letters-bw "videoscale ! video/x-raw,width=1282,height=722 ! \
                       videobox autocrop=true" \
        && fail "Validation succeeded on invalid input"
    return 0
}
test_that_validation_fails_with_vignetting() {
    run_validation letters-bw \
        "rsvgoverlay location=$testdir/vignette-overlay.svg" \
        && fail "Validation succeeded on invalid input"
    return 0
}

# Test manual driver

test_that_validation_video_served_over_http_is_correct() {
    # We test a lot of functionality in this test.  Arguably it should be split
    # down.  We test that:
    #
    # * HTTP URLs are provided.
    # * Videos can be played from those URLs.
    # * The videos are what stbt camera validate was expecting and thus that
    #   the videos have been generated on demand successfully.
    # * The validation code is hooked up to the drivers.
    # * The manual driver responds to user input (pressing <ENTER>).
    #
    # The setup looks like:
    #
    #  |-----------------|          video         |----------------------|
    #  | fakevideosrc.py | --- gst-shm-socket --> | stbt camera validate |
    #  |-----------------|                        |----------------------|
    #          ^ stdin                               ^ stdin        | stderr
    #          |                                     |         instructions
    #          |                            stbt_validate_input     |
    #          |                                     |              V
    #          |                                  |----------------------|
    #    uri_playlist ----------------------------|      this test       |
    #                                             |----------------------|
    #
    # The test listens for instructions from stbt camera validate's stderr and
    # instructs fakevideosrc.py to display URIs before telling stbt camera
    # validate to proceed by pressing enter on it's stdin

    skip_if_no_stbt_camera
    skip_if_no_rsvg_plugins

    start_fake_video_src
    set_config global.control none
    set_config global.transformation_pipeline "videoscale ! video/x-raw,width=1280,height=720 ! identity"

    mkfifo stbt_validate_input
    while cat stbt_validate_input; do true; done | \
        stbt --with-experimental camera validate --tv-driver=manual 2>&1 | (\
        while read line; do
            if [[ "$line" =~ 'http://' ]]; then
                fake_video_src_show "$(echo "$line" | grep -Eo 'http://\S*')"
            fi
            if [[ "$line" =~ 'Press <ENTER>' ]]; then
                sleep 1
                echo >stbt_validate_input
            fi
        done

        # Have to wake the cat up once more to get it to tear itself down
        # properly:
        mv stbt_validate_input stbt_validate_input.teardown
        echo "TEARDOWN" >stbt_validate_input.teardown
        rm stbt_validate_input.teardown
    )
}

# Test illumination compensation

test_illumination_compensation() {
    skip_if_no_stbt_camera
    skip_if_no_rsvg_plugins

    export STBT_TEST_VALIDATION_WAIT_TIMEOUT=60

    set_config global.control none
    start_fake_video_src "$testdir/vignette-overlay.svg" &&
    stbt --with-experimental camera calibrate --noninteractive &&
    start_fake_video_src "$testdir/vignette-overlay.svg" &&
    stbt --with-experimental camera validate
}
