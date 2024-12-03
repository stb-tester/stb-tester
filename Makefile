SHELL := /bin/bash

# The default target of this Makefile is:
all:

prefix?=/usr/local
exec_prefix?=$(prefix)
bindir?=$(exec_prefix)/bin
libexecdir?=$(exec_prefix)/libexec
datarootdir?=$(prefix)/share
mandir?=$(datarootdir)/man
man1dir?=$(mandir)/man1
platform?=x86_64
python_version?=3
pythondir?=$(prefix)/lib/python$(python_version)/site-packages
sysconfdir?=$(prefix)/etc

# Enable building/installing man page
enable_docs:=$(shell which rst2man >/dev/null 2>&1 && echo yes || echo no)
ifeq ($(enable_docs), no)
 $(info Not building/installing documentation because 'rst2man' was not found)
endif

# Enable building/installing stbt virtual-stb
enable_virtual_stb?=no

INSTALL?=install
TAR ?= $(shell which gnutar >/dev/null 2>&1 && echo gnutar || echo tar)
MKTAR = $(TAR) --format=gnu --owner=root --group=root \
    --mtime="$(shell git show -s --format=%ci HEAD)"
GZIP ?= gzip
PYLINT ?= python3 -m pylint
PYTEST ?= python3 -m pytest

CFLAGS?=-O2


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


stbt-control-relay: \
  %: %.in .stbt-prefix VERSION
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@ESCAPED_VERSION@,$(ESCAPED_VERSION),g' \
	    -e 's,@RELEASE@,$(RELEASE),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	     $< > $@

INSTALL_PYLIB_FILES = \
    _stbt/__init__.py \
    _stbt/android.py \
    _stbt/black.py \
    _stbt/config.py \
    _stbt/control.py \
    _stbt/core.py \
    _stbt/cv2_compat.py \
    _stbt/diff.py \
    _stbt/frameobject.py \
    _stbt/grid.py \
    _stbt/gst_hacks.py \
    _stbt/gst_utils.py \
    _stbt/imgproc_cache.py \
    _stbt/imgutils.py \
    _stbt/irnetbox.py \
    _stbt/keyboard.py \
    _stbt/libstbt.py \
    _stbt/libstbt.$(platform).so \
    _stbt/logging.py \
    _stbt/mask.py \
    _stbt/match.py \
    _stbt/motion.py \
    _stbt/multipress.py \
    _stbt/ocr.py \
    _stbt/precondition.py \
    _stbt/power.py \
    _stbt/pylint_plugin.py \
    _stbt/sqdiff.py \
    _stbt/stbt_run.py \
    _stbt/stbt.conf \
    _stbt/transition.py \
    _stbt/types.py \
    _stbt/utils.py \
    _stbt/wait.py \
    _stbt/x-key-mapping.conf \
    _stbt/x11.py \
    _stbt/xorg.conf.in \
    _stbt/xxhash.py \
    stbt_core/__init__.py \
    stbt_core/pylint_plugin.py

INSTALL_CORE_SCRIPTS = \
    stbt_config.py \
    stbt_control.py \
    stbt_lint.py \
    stbt_match.py \
    stbt_power.py \
    stbt_run.py \
    stbt-screenshot \
    stbt-tv

all: $(INSTALL_CORE_SCRIPTS) $(INSTALL_PYLIB_FILES) etc/stbt.conf

INSTALL_VSTB_FILES = \
    stbt_virtual_stb.py

install: install-core
install-core: all
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(pythondir)/stbt_core \
	    $(DESTDIR)$(pythondir)/_stbt \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d \
	    $(DESTDIR)$(libexecdir)/stbt
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	     bin/stbt >$(DESTDIR)$(bindir)/stbt
	chmod 0755 $(DESTDIR)$(bindir)/stbt
	$(INSTALL) -m 0644 stbt-completion \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt
	$(INSTALL) -m 0644 etc/stbt.conf \
	    $(DESTDIR)$(sysconfdir)/stbt/stbt.conf
	$(INSTALL) -m 0755 $(INSTALL_CORE_SCRIPTS) \
	    $(DESTDIR)$(libexecdir)/stbt/
	for filename in $(INSTALL_PYLIB_FILES); do \
	    [ -x "$$filename" ] && mode=0755 || mode=0644; \
	    $(INSTALL) -m $$mode $$filename $(DESTDIR)$(pythondir)/$$filename; \
	done
	printf "sysconfdir = '%s'\n" \
	    "$(sysconfdir)" > $(DESTDIR)$(pythondir)/_stbt/vars.py
	chmod 0644 $(DESTDIR)$(pythondir)/_stbt/vars.py

install-virtual-stb: $(INSTALL_VSTB_FILES)
	$(INSTALL) -m 0755 -d \
	    $(patsubst %,$(DESTDIR)$(libexecdir)/stbt/%,$(sort $(dir $(INSTALL_VSTB_FILES))))
	for filename in $(INSTALL_VSTB_FILES); do \
	    [ -x "$$filename" ] && mode=0755 || mode=0644; \
	    $(INSTALL) -m $$mode $$filename $(DESTDIR)$(libexecdir)/stbt/$$filename; \
	done

INSTALL_GPL_FILES = \
    _stbt/control_gpl.py

install-gpl: $(INSTALL_GPL_FILES)
	$(INSTALL) -m 0755 -d $(DESTDIR)$(pythondir)/_stbt
	for filename in $(INSTALL_GPL_FILES); do \
	    [ -x "$$filename" ] && mode=0755 || mode=0644; \
	    $(INSTALL) -m $$mode $$filename $(DESTDIR)$(pythondir)/$$filename; \
	done

etc/stbt.conf : _stbt/stbt.conf
	# Comment out defaults for /etc/stbt/stbt.conf
	mkdir -p etc
	awk '/^$$/ { print  }; /^#/ { print "#" $$0}; /^\[/ { print $$0 }; /^[^\[#]/ {print "# " $$0 }' _stbt/stbt.conf >$@

STBT_CONTROL_RELAY_PYLIB_FILES = \
    _stbt/__init__.py \
    _stbt/config.py \
    _stbt/control.py \
    _stbt/control_gpl.py \
    _stbt/irnetbox.py \
    _stbt/logging.py \
    _stbt/stbt.conf \
    _stbt/types.py \
    _stbt/utils.py

install-stbt-control-relay: $(STBT_CONTROL_RELAY_PYLIB_FILES) stbt-control-relay
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt-control-relay/_stbt
	$(INSTALL) -m 0755 stbt-control-relay $(DESTDIR)$(bindir)/
	sed '1s,^#!/usr/bin/python\b,#!/usr/bin/python$(python_version),' \
	    stbt_control_relay.py \
	    > $(DESTDIR)$(libexecdir)/stbt-control-relay/stbt_control_relay.py
	chmod 0755 $(DESTDIR)$(libexecdir)/stbt-control-relay/stbt_control_relay.py
	for filename in $(STBT_CONTROL_RELAY_PYLIB_FILES); do \
	    $(INSTALL) -m 0644 $$filename \
	        $(DESTDIR)$(libexecdir)/stbt-control-relay/$$filename; \
	done

uninstall:
	rm -f $(DESTDIR)$(bindir)/stbt
	rm -rf $(DESTDIR)$(libexecdir)/stbt
	rm -f $(DESTDIR)$(man1dir)/stbt.1
	rm -rf $(DESTDIR)$(pythondir)/stbt_core
	rm -rf $(DESTDIR)$(pythondir)/_stbt
	rm -f $(DESTDIR)$(sysconfdir)/stbt/stbt.conf
	rm -f $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/bash_completion.d

clean:
	git clean -Xfd || true

PYTHON_FILES := \
    $(shell git ls-files '*.py' \
      | grep -v -e ^setup.py \
                -e ^vendor/)

check: check-pylint check-pyright check-pytest check-integrationtests
check-pytest: all
	PYTHONPATH=$$PWD:/usr/lib/python$(python_version)/dist-packages/cec \
	STBT_CONFIG_FILE=$$PWD/tests/stbt.conf \
	$(PYTEST) -vv -rs --doctest-modules $(PYTEST_OPTS) \
	    $$(printf "%s\n" $(PYTHON_FILES) |\
	       grep -v -e __init__.py -e tests/vstb-example-html5/ -e ^extra/)
check-pythonpackage:
	export STBT_CONFIG_FILE=$$PWD/tests/stbt.conf && \
	$(PYTEST) -vv -rs $(PYTEST_OPTS) \
	    tests/subdirectory/test_load_image_from_subdirectory.py \
	    tests/test_android.py \
	    tests/test_config.py \
	    tests/test_core.py \
	    tests/test_grid.py \
	    tests/test_match.py \
	    tests/test_motion.py \
	    tests/test_multipress.py \
	    tests/test_transition.py && \
	stbt_lint="pylint --load-plugins=_stbt.pylint_plugin" \
	    tests/run-tests.sh -i tests/test-stbt-lint.sh
check-integrationtests: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" \
	       PYTHONPATH="$$PWD/tests/test-install/lib/python$(python_version)/site-packages:$$PYTHONPATH" && \
	grep -hEo '^test_[a-zA-Z0-9_]+' \
	    $$(ls tests/test-*.sh | \
	       grep -v -e tests/test-virtual-stb.sh) |\
	$(parallel) tests/run-tests.sh -i
check-pylint: all
	PYTHONPATH=$$PWD PYLINT="$(PYLINT)" extra/pylint.sh $(PYTHON_FILES)
check-pyright: all
	PYTHONPATH=$$PWD pyright

ifeq ($(enable_virtual_stb), yes)
install: install-virtual-stb
check: check-virtual-stb
check-virtual-stb: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" \
	       PYTHONPATH="$$PWD/tests/test-install/lib/python$(python_version)/site-packages:$$PYTHONPATH" && \
	tests/run-tests.sh -i tests/test-virtual-stb.sh
else
$(info virtual-stb support disabled)
endif

install-for-test:
	rm -rf tests/test-install && \
	unset MAKEFLAGS prefix exec_prefix bindir libexecdir datarootdir \
	      mandir man1dir pythondir sysconfdir && \
	make install prefix=$$PWD/tests/test-install

parallel ?= $(shell \
    parallel --version 2>/dev/null | grep -q GNU && \
    echo parallel --gnu -j +4 || echo xargs)

tests/ocr/menu.png: %.png: %.svg
	rsvg-convert $< >$@
tests/buttons-on-blue-background.png: tests/buttons.svg
	rsvg-convert $< >$@
tests/buttons.png: tests/buttons.svg
	rsvg-convert <(sed 's/#0000ff/#ffffff/' $<) >$@

# Can only be run from within a git clone of stb-tester or VERSION (and the
# list of files) won't be set correctly.
dist: stb-tester-$(VERSION).tar.gz

DIST = $(shell git ls-files)

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
	etags stbt_core/**.py _stbt/**.py

_stbt/libstbt.$(platform).so : _stbt/sqdiff.c
	$(CC) -shared -fPIC -O3 -o $@ _stbt/sqdiff.c $(CFLAGS)

### Documentation ############################################################

doc: docs/stbt.1

# Requires python-docutils
docs/stbt.1: docs/stbt.1.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	sed -e 's/(callable_,/(`callable_`,/' |\
	rst2man > $@

ifeq ($(enable_docs), yes)
 all: docs/stbt.1
 install-core: install-docs
endif

install-docs: docs/stbt.1
	$(INSTALL) -m 0755 -d $(DESTDIR)$(man1dir)
	$(INSTALL) -m 0644 docs/stbt.1 $(DESTDIR)$(man1dir)

### Docker images for CI #####################################################

CI_DOCKER_IMAGES = ubuntu2204

$(CI_DOCKER_IMAGES:%=.github/workflows/.%.built): .github/workflows/.%.built: .github/workflows/%.dockerfile
	docker build -t stbtester/ci:$* -f .github/workflows/$*.dockerfile \
	    .github/workflows/ && \
	touch $@

ci-docker-images: $(CI_DOCKER_IMAGES:%=.github/workflows/.%.built)
publish-ci-docker-images: $(CI_DOCKER_IMAGES:%=.github/workflows/.%.built)
	set -x && \
	for x in $(CI_DOCKER_IMAGES); do \
	    docker push stbtester/ci:$$x; \
	done

### PyPI Packaging ###########################################################

pypi-publish:
	rm -rf dist/
	python3 setup.py sdist
	twine upload dist/*

### Debian Packaging #########################################################

ubuntu_releases ?= bionic
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
	 debuild -rfakeroot -b $(DPKG_OPTS)) && \
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

.PHONY: all clean deb dist doc install install-core uninstall
.PHONY: check check-integrationtests
.PHONY: check-pytest check-pylint install-for-test
.PHONY: ppa-publish pypi-publish rpm srpm
.PHONY: FORCE TAGS
