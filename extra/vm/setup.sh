#!/bin/bash

# Automated provisioning script run as the `root` user by `vagrant up`
# -- see `./Vagrantfile`.

set -e

install_packages() {
  apt-get install -y \
    lubuntu-desktop \
    virtualbox-guest-dkms virtualbox-guest-utils virtualbox-guest-x11 \
    gstreamer0.10-tools gstreamer0.10-plugins-base \
    gstreamer0.10-plugins-good gstreamer0.10-plugins-bad \
    python-gst0.10 python-opencv python-numpy \
    python-docutils python-nose pep8 pylint expect \
    gstreamer0.10-ffmpeg git moreutils v4l-utils
}
apt-get update
install_packages || {
  /usr/share/debconf/fix_db.pl  # https://bugs.launchpad.net/ubuntu/+bug/873551
  install_packages
}

usermod -a -G video vagrant

sudo su - vagrant /vagrant/setup-vagrant-user.sh
