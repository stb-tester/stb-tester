#!/bin/sh

. $testdir/utils.sh

case $1 in
    start)
        set_config global.source_pipeline \
            "decklinksrc mode=1080p30 connection=hdmi ! videoconvert"
        ;;
    stop)
        ;;
esac
