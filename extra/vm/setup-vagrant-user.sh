#!/bin/bash

# Automated provisioning script run as the `vagrant` user by `vagrant up`
# -- see `./Vagrantfile` and `./setup.sh`.

set -e

# Bash tab-completion
cat > ~/.bash_completion <<-'EOF'
	for f in ~/etc/bash_completion.d/*; do source $f; done
	EOF
mkdir -p ~/etc/bash_completion.d
wget -q -O ~/etc/bash_completion.d/gstreamer-completion-1.2.4 \
  http://cgit.freedesktop.org/gstreamer/gstreamer/plain/tools/gstreamer-completion?id=1.2.4

sed -i '/### stb-tester configuration ###/,$ d' ~/.bashrc
cat >> ~/.bashrc <<-EOF
	### stb-tester configuration ###
	export DISPLAY=:0
	! [ -r /dev/video0 ] ||
	    v4l2-ctl --set-ctrl=brightness=128,contrast=64,saturation=64,hue=15
	EOF

mkdir -p ~/.config/stbt
cat > ~/.config/stbt/stbt.conf <<-EOF
	[global]
	# Source pipeline for the Hauppauge HD PVR video-capture device.
	#source_pipeline = v4l2src device=/dev/video0 ! tsdemux ! h264parse
	
	# Handle loss of video (but without end-of-stream event) from the video
	# capture device. Set to "True" if you're using the Hauppauge HD PVR.
	restart_source = False
	
	# Source pipeline for the Teradek VidiU streaming video-capture device.
	#source_pipeline = rtmpsrc location=rtmp://localhost/live/stream-name\ live=1
	
	sink_pipeline = ximagesink sync=false
	#control = lirc::remote_name
	
	[run]
	#save_video = video.webm
	EOF
