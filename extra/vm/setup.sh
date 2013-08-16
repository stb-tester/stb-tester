#!/bin/bash

# Automated provisioning script run as the `root` user by `vagrant up`
# -- see `./Vagrantfile`.

set -e

install_packages() {
  local packages
  # X11 environment so that you can use `ximagesink`
  packages=lubuntu-desktop
  # VirtualBox guest additions for shared folders, USB, window resizing, etc.
  packages+=" virtualbox-guest-dkms virtualbox-guest-utils virtualbox-guest-x11"
  # Core stbt dependencies
  packages+=" gstreamer0.10-tools gstreamer0.10-plugins-base"
  packages+=" gstreamer0.10-plugins-good gstreamer0.10-plugins-bad"
  packages+=" python-gst0.10 python-opencv python-numpy"
  # For `stbt power`
  packages+=" curl expect openssh-client"
  # For `extra/runner`
  packages+=" lsof moreutils python-flask python-jinja2"
  # For building stbt and running the self-tests
  packages+=" git pep8 pylint python-docutils python-nose"
  # For the Hauppauge HDPVR
  packages+=" gstreamer0.10-ffmpeg v4l-utils"

  apt-get install -y $packages
}

apt-get update
install_packages || {
  /usr/share/debconf/fix_db.pl  # https://bugs.launchpad.net/ubuntu/+bug/873551
  install_packages
}

# Kernel >= 3.3 for the RedRat3 USB infrared emitter
# Note that xserver-xorg-lts-quantal conflicts with virtualbox-guest-x11:
# https://bugs.launchpad.net/ubuntu/+source/virtualbox/+bug/1160401
apt-get install -y linux-generic-lts-quantal

usermod -a -G video vagrant

sudo su - vagrant /vagrant/setup-vagrant-user.sh
