#!/bin/sh

this_dir=$(dirname $(readlink -f $0))

chromium-browser --temp-profile --no-sandbox --disable-gpu \
    --app=file://$this_dir/virtual-stb/index.html
