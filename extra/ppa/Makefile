DPUT_HOST?=ppa:stb-tester
DEBUILD_OPTS=

UVC_RELEASE=1.4

VER=1.2.0
REL=1ubuntu1
NEWREL=2~stbtester2
DISTRO=saucy

all:

SOURCES = $(LINUX_SOURCES) $(GST_SOURCES)
PATCHES = $(LINUX_PATCHES) $(GST_PATCHES)
DOWNLOADS = $(SOURCES) $(PATCHES)
FOR_UPLOAD = \
	gst-plugins-good1.0/gst-plugins-good1.0_$(VER)-$(NEWREL)_source.changes \
	uvcvideo-dkms_$(UVC_RELEASE)_source.changes

all : $(FOR_UPLOAD)

upload : $(FOR_UPLOAD)
	for x in $^; do \
		dput $(DPUT_HOST) $$x; \
	done

download : $(SOURCES) $(GST_PATCHES)

clean :
	git clean -fdX $(patsubst %,-e "!%",$(DOWNLOADS)) .

really-clean :
	git clean -fdX .

.PHONY : all clean download really-clean upload

export DEBFULLNAME:=$(shell git config user.name)
export DEBEMAIL:=$(shell git config user.email)

###########################

GST_SOURCES=\
	gst-plugins-good1.0_$(VER)-$(REL).dsc \
	gst-plugins-good1.0_$(VER).orig.tar.xz \
	gst-plugins-good1.0_$(VER)-$(REL).debian.tar.gz

GST_PATCHES=\
	0001-v4l2-normalise-control-names-in-the-same-way-as-v4l2-ctl.patch \
	0002-v4l2src-fix-support-for-mpegts-streams.patch \
	0003-v4l2src-only-care-about-getting-correct-width-height-if-in-caps.patch

gst-plugins-good1.0 :
	mkdir -p $@

gst-plugins-good1.0/gst-plugins-good1.0_$(VER)-$(NEWREL)_source.changes : $(GST_SOURCES) $(GST_PATCHES)
	rm -rf "gst-plugins-good1.0" && \
	mkdir -p gst-plugins-good1.0 && \
	cp $(GST_SOURCES) gst-plugins-good1.0 && \
	cd gst-plugins-good1.0 && \
	dpkg-source -x gst-plugins-good1.0_$(VER)-$(REL).dsc && \
	cd gst-plugins-good1.0-$(VER) && \
	QUILT_PATCHES=debian/patches quilt import $(abspath $(GST_PATCHES)) && \
	dch -v $(VER)-$(NEWREL) "Backport fixes to allow stb-tester to work" && \
	dch -r --distribution $(DISTRO) "" && \
	debuild -S -i $(DEBUILD_OPTS)

0001-v4l2-normalise-control-names-in-the-same-way-as-v4l2-ctl.patch :
	wget https://bug725632.bugzilla-attachments.gnome.org/attachment.cgi?id=271392 -O $@

0002-v4l2src-fix-support-for-mpegts-streams.patch :
	wget https://bug725860.bugzilla-attachments.gnome.org/attachment.cgi?id=271165 -O $@

0003-v4l2src-only-care-about-getting-correct-width-height-if-in-caps.patch :
	wget https://bug725860.bugzilla-attachments.gnome.org/attachment.cgi?id=271151 -O $@

##########################

LINUX_SOURCES = \
	linux_3.11.0-18.32.dsc \
	linux_3.11.0.orig.tar.gz \
	linux_3.11.0-18.32.diff.gz

LINUX_PATCHES = \
	uvcvideo-work-around-buggy-logitech-c920-firmware.patch

uvcvideo-work-around-buggy-logitech-c920-firmware.patch :
	wget http://download.gmane.org/gmane.linux.drivers.video-input-infrastructure/75696/75697 -O $@

uvcvideo : $(LINUX_SOURCES) $(LINUX_PATCHES)
	rm -rf linux uvcvideo && \
	mkdir linux && \
	cp $^ linux && \
	cd linux && \
	dpkg-source -x linux_3.11.0-18.32.dsc && \
	cd linux-3.11.0 && \
	patch -p1 < ../../uvcvideo-work-around-buggy-logitech-c920-firmware.patch && \
	sed -E --in-place 's/#define DRIVER_VERSION\s+"(.*)"/#define DRIVER_VERSION "\1-stbtester1"/' \
		drivers/media/usb/uvc/uvcvideo.h && \
	rm -f drivers/media/usb/uvc/*.orig && \
	cp -r drivers/media/usb/uvc $(abspath $@)

uvcvideo-dkms_$(UVC_RELEASE)_source.changes : uvcvideo
	rm -rf uvcvideo-dkms && \
	cp -r uvcvideo uvcvideo-dkms && \
	cd uvcvideo-dkms && \
	SOURCES="$$(echo $$(ls))" && \
	dh_make -y --single --packagename uvcvideo-dkms_$(UVC_RELEASE) --native --copyright gpl2 && \
	rm debian/*.ex debian/*.EX debian/README* && \
	sed "s,@SOURCES@,$$SOURCES,g" ../uvcvideo-dkms-rules.in >debian/rules && \
	sed -Ei "s/(Depends.*)/\1, dkms/" debian/control && \
	sed -i 's!<insert the upstream URL, if relevant>!http://kernel.org/!g' debian/control && \
	sed -i 's/<insert up to 60 chars description>/Kernel modules for UVC webcams/g' debian/control && \
	sed -i 's/<insert long description, indented with spaces>/With a patch applied to work-around Logitech C920 firmware bugs/g' debian/control && \
	sed -i 's/Section: unknown/Section: misc/g' debian/control && \
	cp ../uvcvideo-dkms.dkms debian/uvcvideo-dkms.dkms && \
	dch -v $(UVC_RELEASE) "" && \
	dch -r --distribution $(DISTRO) "Fixed" && \
	debuild -S -i $(DEBUILD_OPTS)

############################

$(SOURCES) : % :
	first_char=$$(echo $@ | head -c 1) && \
	wget -P $(dir $@) http://archive.ubuntu.com/ubuntu/pool/main/$$first_char/$(firstword $(subst _, ,$@))/$(notdir $@)
