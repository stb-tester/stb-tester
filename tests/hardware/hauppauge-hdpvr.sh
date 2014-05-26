#!/bin/sh

. $testdir/utils.sh

case $1 in
    start)
        set_config global.v4l2_device \
            "/dev/v4l/by-id/usb-AMBA_Hauppauge_HD_PVR_00A776F7-video-index0"
        set_config global.source_pipeline \
            "v4l2src device=%(v4l2_device)s ! tsdemux ! h264parse"
        ;;
    stop)
        ;;

esac
