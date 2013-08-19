#!/bin/bash

# Automated provisioning script run as the `vagrant` user by `vagrant up`
# -- see `./Vagrantfile` and `./setup.sh`.

set -e

stbt_version=0.15

# Install stbt to ~/bin
tmpdir=$(mktemp -d)
trap 'rm -rf $tmpdir' EXIT
git clone ~/stb-tester $tmpdir
cd $tmpdir
git checkout $stbt_version
make prefix=$HOME install
# Apply fix from master https://github.com/drothlis/stb-tester/commit/799067a2
sed -i 's/grep -q VMware/grep -Eq "VMware|VirtualBox"/' ~/libexec/stbt/stbt-tv

# Bash tab-completion
cat > ~/.bash_completion <<-'EOF'
	for f in ~/etc/bash_completion.d/*; do source $f; done
	EOF
mkdir -p ~/etc/bash_completion.d
wget -q -O ~/etc/bash_completion.d/gstreamer-completion-0.10 \
  https://raw.github.com/drothlis/gstreamer/bash-completion-0.10/tools/gstreamer-completion-0.10

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
	#source_pipeline = v4l2src device=/dev/video0 ! mpegtsdemux ! video/x-h264 ! decodebin2
	
	# Handle loss of video (but without end-of-stream event) from the video
	# capture device. Set to "True" if you're using the Hauppauge HD PVR.
	#restart_source = False
	
	sink_pipeline = ximagesink sync=false
	#control = lirc::remote_name
	
	[run]
	#save_video = video.webm
	EOF
