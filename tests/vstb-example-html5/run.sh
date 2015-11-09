#!/bin/sh

this_dir=$(dirname $(readlink -f $0))

chromium-browser --no-sandbox --app=file://$this_dir/virtual-stb/index.html
