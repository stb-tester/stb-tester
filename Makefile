# The default target of this Makefile is:
all:

PKG_DEPS=gstreamer-1.0 gstreamer-app-1.0 gstreamer-video-1.0 opencv orc-0.4

prefix?=/usr/local
exec_prefix?=$(prefix)
bindir?=$(exec_prefix)/bin
libexecdir?=$(exec_prefix)/libexec
datarootdir?=$(prefix)/share
mandir?=$(datarootdir)/man
man1dir?=$(mandir)/man1
sysconfdir?=$(prefix)/etc

# Support installing GStreamer elements under $HOME
gsthomepluginsdir=$(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)/gstreamer-1.0/plugins
gstsystempluginsdir=$(shell pkg-config --variable=pluginsdir gstreamer-1.0)
gstpluginsdir?=$(if $(filter $(HOME)%,$(prefix)),$(gsthomepluginsdir),$(gstsystempluginsdir))

# Enable building/installing man page
enable_docs:=$(shell which rst2man >/dev/null 2>&1 && echo yes || echo no)
ifeq ($(enable_docs), no)
 $(info Not building/installing documentation because 'rst2man' was not found)
endif

# Enable building/installing stbt camera (smart TV support).
enable_stbt_camera?=no

INSTALL?=install
TAR ?= $(shell which gnutar >/dev/null 2>&1 && echo gnutar || echo tar)
MKTAR = $(TAR) --format=gnu --owner=root --group=root \
    --mtime="$(shell git show -s --format=%ci HEAD)"
GZIP ?= gzip

tools = stbt-run
tools += stbt-record
tools += stbt-batch
tools += stbt-config
tools += stbt-control
tools += stbt-lint
tools += stbt-power
tools += stbt-screenshot
tools += stbt-templatematch
tools += stbt-tv

# Generate version from 'git describe' when in git repository, and from
# VERSION file included in the dist tarball otherwise.
generate_version := $(shell \
	GIT_DIR=.git git describe --always --dirty > VERSION.now 2>/dev/null && \
	perl -pi -e 's/^v//' VERSION.now && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)
VERSION?=$(shell cat VERSION)
ESCAPED_VERSION=$(subst -,_,$(VERSION))
RELEASE?=1

.DELETE_ON_ERROR:


all: stbt.sh defaults.conf extra/fedora/stb-tester.spec

extra/fedora/stb-tester.spec stbt.sh: \
  %: %.in .stbt-prefix VERSION
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@ESCAPED_VERSION@,$(ESCAPED_VERSION),g' \
	    -e 's,@RELEASE@,$(RELEASE),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' \
	     $< > $@

defaults.conf: stbt.conf .stbt-prefix
	perl -lpe \
	    '/\[global\]/ && ($$_ .= "\n__system_config=$(sysconfdir)/stbt/stbt.conf")' \
	    $< > $@

install: install-core
install-core: stbt.sh defaults.conf
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt \
	    $(DESTDIR)$(libexecdir)/stbt/_stbt \
	    $(DESTDIR)$(libexecdir)/stbt/stbt \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/static \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/templates \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d
	$(INSTALL) -m 0755 stbt.sh $(DESTDIR)$(bindir)/stbt
	$(INSTALL) -m 0755 irnetbox-proxy $(DESTDIR)$(bindir)
	$(INSTALL) -m 0755 $(tools) $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 \
	    _stbt/__init__.py \
	    _stbt/config.py \
	    _stbt/control.py \
	    _stbt/core.py \
	    _stbt/gst_hacks.py \
	    _stbt/irnetbox.py \
	    _stbt/logging.py \
	    _stbt/power.py \
	    _stbt/pylint_plugin.py \
	    _stbt/state_watch.py \
	    _stbt/stbt-power.sh \
	    _stbt/utils.py \
	    $(DESTDIR)$(libexecdir)/stbt/_stbt
	$(INSTALL) -m 0644 stbt/__init__.py $(DESTDIR)$(libexecdir)/stbt/stbt
	$(INSTALL) -m 0644 defaults.conf $(DESTDIR)$(libexecdir)/stbt/stbt.conf
	$(INSTALL) -m 0755 \
	    stbt-batch.d/run.py \
	    stbt-batch.d/run-one \
	    stbt-batch.d/report \
	    stbt-batch.d/instaweb \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d
	$(INSTALL) -m 0644 stbt-batch.d/report.py \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d
	$(INSTALL) -m 0644 stbt-batch.d/static/edit-testrun.js \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/static
	$(INSTALL) -m 0644 \
	    stbt-batch.d/templates/directory-index.html \
	    stbt-batch.d/templates/index.html \
	    stbt-batch.d/templates/testrun.html \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/templates
	$(INSTALL) -m 0644 stbt.conf $(DESTDIR)$(sysconfdir)/stbt
	$(INSTALL) -m 0644 stbt-completion \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt

uninstall:
	rm -f $(DESTDIR)$(bindir)/stbt
	rm -f $(DESTDIR)$(bindir)/irnetbox-proxy
	rm -rf $(DESTDIR)$(libexecdir)/stbt
	rm -f $(DESTDIR)$(man1dir)/stbt.1
	rm -f $(DESTDIR)$(sysconfdir)/stbt/stbt.conf
	rm -f $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/bash_completion.d

clean:
	git clean -Xfd || true

PYTHON_FILES = $(shell (git ls-files '*.py' && \
           git grep --name-only -E '^\#!/usr/bin/(env python|python)') \
           | sort | uniq)

check: check-pylint check-nosetests check-integrationtests check-bashcompletion
check-nosetests: tests/ocr/menu.png
	# Workaround for https://github.com/nose-devs/nose/issues/49:
	cp stbt-control nosetest-issue-49-workaround-stbt-control.py && \
	PYTHONPATH=$$PWD NOSE_REDNOSE=1 \
	nosetests --with-doctest -v --match "^test_" \
	    --doctest-options=+ELLIPSIS \
	    $(shell git ls-files '*.py' |\
	      grep -v -e tests/test.py \
	              -e tests/test2.py \
	              -e tests/test_functions.py) \
	    nosetest-issue-49-workaround-stbt-control.py && \
	rm nosetest-issue-49-workaround-stbt-control.py
check-integrationtests: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" && \
	grep -hEo '^test_[a-zA-Z0-9_]+' \
	    $$(ls tests/test-*.sh | grep -v tests/test-camera.sh) |\
	$(parallel) tests/run-tests.sh -i
check-hardware: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" && \
	tests/run-tests.sh -i tests/hardware/test-hardware.sh
check-pylint:
	printf "%s\n" $(PYTHON_FILES) \
	| PYTHONPATH=$$PWD $(parallel) extra/pylint.sh
check-bashcompletion:
	@echo Running stbt-completion unit tests
	@bash -c ' \
	    set -e; \
	    . ./stbt-completion; \
	    for t in `declare -F | awk "/_stbt_test_/ {print \\$$3}"`; do \
	        ($$t); \
	    done'

ifeq ($(enable_stbt_camera), yes)
check: check-cameratests
check-cameratests: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" \
	       GST_PLUGIN_PATH=$$PWD/tests/test-install/lib/gstreamer-1.0/plugins:$$GST_PLUGIN_PATH && \
	tests/run-tests.sh -i tests/test-camera.sh
endif

install-for-test:
	rm -rf tests/test-install && \
	unset MAKEFLAGS prefix exec_prefix bindir libexecdir datarootdir \
	      gstpluginsdir mandir man1dir sysconfdir && \
	make install prefix=$$PWD/tests/test-install \
	     gstpluginsdir=$$PWD/tests/test-install/lib/gstreamer-1.0/plugins

parallel := $(shell \
    parallel --version 2>/dev/null | grep -q GNU && \
    echo parallel --gnu -j +4 || echo xargs)

tests/ocr/menu.png: %.png: %.svg
	rsvg-convert $< >$@

# Can only be run from within a git clone of stb-tester or VERSION (and the
# list of files) won't be set correctly.
dist: stb-tester-$(VERSION).tar.gz

DIST = $(shell git ls-files)
DIST += VERSION

stb-tester-$(VERSION).tar.gz: $(DIST)
	@$(TAR) --version 2>/dev/null | grep -q GNU || { \
	    printf 'Error: "make dist" requires GNU tar ' >&2; \
	    printf '(use "make dist TAR=gnutar").\n' >&2; \
	    exit 1; }
	# Separate tar and gzip so we can pass "-n" for more deterministic
	# tarball generation
	$(MKTAR) -c --transform='s,^,stb-tester-$(VERSION)/,' \
	         -f stb-tester-$(VERSION).tar $^ && \
	$(GZIP) -9fn stb-tester-$(VERSION).tar


# Force rebuild if installation directories change
sq = $(subst ','\'',$(1)) # function to escape single quotes (')
.stbt-prefix: flags = libexecdir=$(call sq,$(libexecdir)):\
                      sysconfdir=$(call sq,$(sysconfdir))
.stbt-prefix: FORCE
	@if [ '$(flags)' != "$$(cat $@ 2>/dev/null)" ]; then \
	    [ -f $@ ] && echo "*** new $@" >&2; \
	    echo '$(flags)' > $@; \
	fi

TAGS:
	etags stbt/**.py _stbt/**.py

### Documentation ############################################################

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	sed -e '/\.\. image::/,/^$$/ d' |\
	sed -e 's/(callable_,/(`callable_`,/' |\
	rst2man > $@

ifeq ($(enable_docs), yes)
 all: stbt.1
 install-core: install-docs
endif

install-docs: stbt.1
	$(INSTALL) -m 0755 -d $(DESTDIR)$(man1dir)
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(man1dir)

### Debian Packaging #########################################################

ubuntu_releases ?= trusty vivid wily
DPKG_OPTS?=
debian_base_release=1
debian_architecture=$(shell dpkg --print-architecture 2>/dev/null)
DPUT_HOST?=ppa:stb-tester/stb-tester

# In the following rules, "%" and "$*" stand for the release number: "1" when
# building a debian unstable package, or "1~trusty" or "1~utopic" (etc) when
# building an ubuntu package.

# deb: stb-tester_22-1_amd64.deb
deb: stb-tester_$(VERSION)-$(debian_base_release)_$(debian_architecture).deb

# Build debian source packages for debian unstable and all $(ubuntu_releases).
debsrc: \
  debian-packages/stb-tester_$(VERSION)-$(debian_base_release).dsc \
  $(ubuntu_releases:%=debian-packages/stb-tester_$(VERSION)-$(debian_base_release)~%.dsc)

# Publish all $(ubuntu_releases) source packages to stb-tester PPA
ppa-publish: $(ubuntu_releases:%=ppa-publish-$(debian_base_release)~%)

ppa-publish-%: debian-packages/stb-tester_$(VERSION)-%.dsc
	dput $(DPUT_HOST) \
	    debian-packages/stb-tester_$(VERSION)-$*_source.changes

# Build debian source package
debian-packages/stb-tester_$(VERSION)-%.dsc: \
  stb-tester-$(VERSION).tar.gz extra/debian/changelog.in
	extra/debian/build-source-package.sh $(VERSION) $*

# Build debian binary package from source package
# stb-tester_22-1_amd64.deb: debian-packages/stb-tester_22-1.dsc
stb-tester_$(VERSION)-%_$(debian_architecture).deb: \
  debian-packages/stb-tester_$(VERSION)-%.dsc
	tmpdir=$$(mktemp -dt stb-tester-deb-build.XXXXXX) && \
	dpkg-source -x $< $$tmpdir/source && \
	(cd "$$tmpdir/source" && \
	 DEB_BUILD_OPTIONS=nocheck \
	 dpkg-buildpackage -rfakeroot -b $(DPKG_OPTS)) && \
	mv "$$tmpdir"/*.deb . && \
	rm -rf "$$tmpdir"

### Fedora Packaging #########################################################

rpm_topdir?=$(HOME)/rpmbuild
src_rpm=stb-tester-$(ESCAPED_VERSION)-$(RELEASE)$(shell rpm -E %dist 2>/dev/null).src.rpm

srpm: $(src_rpm)

$(src_rpm): stb-tester-$(VERSION).tar.gz extra/fedora/stb-tester.spec
	@printf "\n*** Building Fedora src rpm ***\n"
	mkdir -p $(rpm_topdir)/SOURCES
	cp stb-tester-$(VERSION).tar.gz $(rpm_topdir)/SOURCES
	rpmbuild --define "_topdir $(rpm_topdir)" -bs extra/fedora/stb-tester.spec
	mv $(rpm_topdir)/SRPMS/$(src_rpm) .

rpm: $(src_rpm)
	sudo dnf builddep -y $<
	rpmbuild --define "_topdir $(rpm_topdir)" --rebuild $<
	mv $(rpm_topdir)/RPMS/*/stb-tester-* .

### stbt camera - Optional Smart TV support ##################################

ifeq ($(enable_stbt_camera), yes)
all: stbt-camera.d/gst/stbt-gst-plugins.so
install: install-stbt-camera
else
$(info Smart TV support disabled)
endif

stbt_camera_files=\
	_stbt/gst_utils.py \
	_stbt/tv_driver.py \
	stbt-camera \
	stbt-camera.d/chessboard-720p-40px-border-white.png \
	stbt-camera.d/colours.svg \
	stbt-camera.d/glyphs.svg.jinja2 \
	stbt-camera.d/stbt-camera-calibrate.py \
	stbt-camera.d/stbt-camera-validate.py

installed_camera_files=\
	$(stbt_camera_files:%=$(DESTDIR)$(libexecdir)/stbt/%) \
	$(DESTDIR)$(gstpluginsdir)/stbt-gst-plugins.so

CFLAGS?=-O2

%_orc.h: %.orc
	orcc --header --internal -o "$@" "$<"
%_orc.c: %.orc
	orcc --implementation --internal -o "$@" "$<"

stbt-camera.d/gst/stbt-gst-plugins.so: stbt-camera.d/gst/stbtgeometriccorrection.c \
                                       stbt-camera.d/gst/stbtgeometriccorrection.h \
                                       stbt-camera.d/gst/plugin.c \
                                       stbt-camera.d/gst/stbtcontraststretch.c \
                                       stbt-camera.d/gst/stbtcontraststretch.h \
                                       stbt-camera.d/gst/stbtcontraststretch_orc.c \
                                       stbt-camera.d/gst/stbtcontraststretch_orc.h \
                                       VERSION
	@if ! pkg-config --exists $(PKG_DEPS); then \
		printf "Please install packages $(PKG_DEPS)\n"; \
		if which apt-file >/dev/null 2>&1; then \
			PACKAGES=$$(printf "/%s.pc\n" $(PKG_DEPS) | apt-file search -fl) ; \
			echo Try apt install $$PACKAGES; \
		fi; \
		exit 1; \
	fi
	gcc -shared -o $@ $(filter %.c %.o,$^) -fPIC  -Wall -Werror $(CFLAGS) \
		$(LDFLAGS) $$(pkg-config --libs --cflags $(PKG_DEPS)) \
		-DVERSION=\"$(VERSION)\"

install-stbt-camera: $(stbt_camera_files) stbt-camera.d/gst/stbt-gst-plugins.so
	$(INSTALL) -m 0755 -d $(sort $(dir $(installed_camera_files)))
	@for file in $(stbt_camera_files); \
	do \
		if [ -x "$$file" ]; then \
			perms=0755; \
		else \
			perms=0644; \
		fi; \
		echo INSTALL "$$file"; \
		$(INSTALL) -m $$perms "$$file" "$(DESTDIR)$(libexecdir)/stbt/$$file"; \
	done
	$(INSTALL) -m 0644 stbt-camera.d/gst/stbt-gst-plugins.so \
		$(DESTDIR)$(gstpluginsdir)

.PHONY: all clean deb dist doc install install-core uninstall
.PHONY: check check-bashcompletion check-hardware check-integrationtests
.PHONY: check-nosetests check-pylint install-for-test
.PHONY: ppa-publish rpm srpm
.PHONY: check-cameratests install-stbt-camera
.PHONY: FORCE TAGS
