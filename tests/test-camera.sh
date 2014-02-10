# Run with ./run-tests.sh

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
