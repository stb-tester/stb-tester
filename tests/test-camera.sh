# Run with ./run-tests.sh

skip_if_no_rsvg_plugins() {
    if ! gst-inspect-1.0 rsvg 2>&1 >/dev/null; then
        echo "SKIP: Skipping test as rsvg plugins not installed"
        exit 77
    fi
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

    rm gst-shm-socket
    mkfifo uri_playlist
    while cat uri_playlist; do true; done | \
        PYTHONPATH=$testdir/..:$PYTHONPATH "$testdir/fake-video-src.py" "$PWD/gst-shm-socket" &
    FAKE_VIDEO_SRC_PID=$!
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
    rm gst-shm-socket
    gst-launch-1.0 "$@" \
        ! video/x-raw,format=RGB,width=$WIDTH,height=$HEIGHT,framerate=25/1 \
        ! queue ! shmsink "wait-for-connection=true" "shm-size=$shm_size" \
          socket-path=$PWD/gst-shm-socket blocksize=$frame_bytes sync=true \
          buffer-time=100000000 &
    FAKE_VIDEO_SRC_PID=$!
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
    rm uri_playlist gst-shm-socket
    true
}

###
### stbt camera validate tests
###

run_validation() {
    color="$1"
    extra=${2:-identity}

    skip_if_no_rsvg_plugins

    start_fake_video_src_launch_720 filesrc location=$testdir/$1.png ! pngdec \
        ! videoconvert ! $extra ! videoconvert \
        ! video/x-raw,width=1280,height=720 ! imagefreeze &&
    set_config global.control none &&
    stbt --with-experimental camera validate --tv-driver=assume "$1" &&
    stop_fake_video_src
}

test_that_validation_passes_on_pristine_input() {
    run_validation letters-bw "" || fail "Validation failed on pristine input"
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

    stop_fake_video_src
}
