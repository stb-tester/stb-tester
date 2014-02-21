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
  packages+=" gstreamer1.0-tools gstreamer1.0-plugins-base"
  packages+=" gstreamer1.0-plugins-good gstreamer1.0-plugins-bad"
  packages+=" python-gobject gir1.2-gstreamer-1.0 python-opencv python-numpy"
  packages+=" tesseract-ocr"
  # For `stbt power`
  packages+=" curl expect openssh-client"
  # For `stbt batch`
  packages+=" lsof moreutils python-flask python-jinja2"
  # For building stbt and running the self-tests
  packages+=" git pep8 pylint python-docutils python-nose"
  # For the Hauppauge HDPVR
  packages+=" gstreamer1.0-libav v4l-utils"

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

DEBIAN_FRONTEND=noninteractive apt-get install -y lirc
sed -i \
    -e 's,^START_LIRCD="false",START_LIRCD="true",' \
    -e 's,^REMOTE_DEVICE=".*",REMOTE_DEVICE="/dev/lirc0",' \
    /etc/lirc/hardware.conf
service lirc start
# You still need to install /etc/lirc/lircd.conf with a description of your
# remote control's infrared protocol. See http://stb-tester.com/lirc.html

# HDPVR and other V4L devices
usermod -a -G video vagrant

# VidiU (RTMP streaming device)
apt-get install -y crtmpserver
[ -f /etc/crtmpserver/crtmpserver.lua.orig ] ||
    cp /etc/crtmpserver/crtmpserver.lua{,.orig}
cp /vagrant/crtmpserver.lua /etc/crtmpserver/
service crtmpserver restart &>/dev/null </dev/null ||
    echo error restarting crtmpserver >&2
service ufw stop &>/dev/null </dev/null || echo error stopping ufw firewall >&2

sudo su - vagrant /vagrant/setup-vagrant-user.sh
