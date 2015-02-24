#!/bin/bash

# Instructions to build gstreamer1-plugins-good RPM on Fedora 19/20
# with fix for https://bugzilla.gnome.org/show_bug.cgi?id=725860

set -e

source /etc/os-release
FEDORA_VERSION=$VERSION_ID
case "$FEDORA_VERSION" in
    19) GST_VERSION=1.0.10-1.fc19;;
    20) GST_VERSION=1.2.3-2.fc20;;
    *) echo "Unknown Fedora version"; false;;
esac

rm -rf gstreamer1-plugins-good
mkdir gstreamer1-plugins-good
cd gstreamer1-plugins-good

wget https://dl.fedoraproject.org/pub/fedora/linux/updates/$FEDORA_VERSION/SRPMS/gstreamer1-plugins-good-$GST_VERSION.src.rpm
wget https://bug725632.bugzilla-attachments.gnome.org/attachment.cgi?id=271392 -O 0001-v4l2-normalise-control-names-in-the-same-way-as-v4l2-ctl.patch
wget https://bug725860.bugzilla-attachments.gnome.org/attachment.cgi?id=271165 -O 0002-v4l2src-fix-support-for-mpegts-streams.patch
wget https://bug725860.bugzilla-attachments.gnome.org/attachment.cgi?id=271151 -O 0003-v4l2src-only-care-about-getting-correct-width-height-if-in-caps.patch

rpm2cpio gstreamer1-plugins-good-$GST_VERSION.src.rpm | cpio -idmv
patch -p0 < ../gstreamer1-plugins-good.spec.$FEDORA_VERSION.patch
rm -f gstreamer1-plugins-good-$GST_VERSION.src.rpm

rpm_topdir=$HOME/rpmbuild
mkdir -p $rpm_topdir/SOURCES
cp gst-plugins-good-*.tar.xz *.patch $rpm_topdir/SOURCES/
rpmbuild --define "_topdir $rpm_topdir" -bs gstreamer1-plugins-good.spec

# Verify SRPM locally
yum-builddep -y $rpm_topdir/SRPMS/gstreamer1-plugins-good-$GST_VERSION.stbtester1.src.rpm
rpmbuild --define "_topdir $rpm_topdir" -bb gstreamer1-plugins-good.spec

# Host SRPM on webserver so that Copr buildsystem can find it
git clone git@github.com:stb-tester/stb-tester-srpms.git
cd stb-tester-srpms
mv ~/rpmbuild/SRPMS/gstreamer1-plugins-good-$GST_VERSION.stbtester1.src.rpm .
git add gstreamer1-plugins-good-$GST_VERSION.stbtester1.src.rpm
git commit -m "gstreamer1-plugins-good-$GST_VERSION.stbtester1.src.rpm

Patched gstreamer1-plugins-good for Fedora $FEDORA_VERSION

With the patches for https://bugzilla.gnome.org/show_bug.cgi?id=725860
to support the HDPVR with GStreamer 1.x.

These patches have been merged upstream and should be available in
gstreamer1-plugins-good 1.2.4 or 1.2.5 in the near future. In the
meantime you can use this package, published at
http://copr.fedoraproject.org/coprs/stbt/stb-tester/
"
git push origin master

# Now add to http://copr.fedoraproject.org/coprs/stbt/stb-tester/add_build/
# TODO: Do it with copr-cli
