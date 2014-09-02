# The default target of this Makefile is:
all:

prefix?=/usr/local
exec_prefix?=$(prefix)
bindir?=$(exec_prefix)/bin
libexecdir?=$(exec_prefix)/libexec
datarootdir?=$(prefix)/share
mandir?=$(datarootdir)/man
man1dir?=$(mandir)/man1
sysconfdir?=$(prefix)/etc

user_name?=$(shell git config user.name || \
                   getent passwd `whoami` | cut -d : -f 5 | cut -d , -f 1)
user_email?=$(shell git config user.email || echo "$$USER@$$(hostname)")

ubuntu_releases ?= saucy trusty
debian_base_release=1

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
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)
VERSION?=$(shell cat VERSION)
ESCAPED_VERSION=$(subst -,_,$(VERSION))

.DELETE_ON_ERROR:


all: stbt.sh stbt.1 defaults.conf extra/fedora/stb-tester.spec

extra/fedora/stb-tester.spec extra/debian/changelog stbt.sh : % : %.in .stbt-prefix VERSION
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@ESCAPED_VERSION@,$(ESCAPED_VERSION),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' \
	    -e "s/@RFC_2822_DATE@/$$(git show -s --format=%aD HEAD)/g" \
	    -e 's,@USER_NAME@,$(user_name),g' \
	    -e 's,@USER_EMAIL@,$(user_email),g' \
	     $< > $@

defaults.conf: stbt.conf .stbt-prefix
	perl -lpe \
	    '/\[global\]/ && ($$_ .= "\n__system_config=$(sysconfdir)/stbt/stbt.conf")' \
	    $< > $@

install: stbt.sh stbt.1 defaults.conf
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt \
	    $(DESTDIR)$(libexecdir)/stbt/stbt \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/static \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/templates \
	    $(DESTDIR)$(man1dir) \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d
	$(INSTALL) -m 0755 stbt.sh $(DESTDIR)$(bindir)/stbt
	$(INSTALL) -m 0755 irnetbox-proxy $(DESTDIR)$(bindir)
	$(INSTALL) -m 0755 $(tools) $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 \
	    stbt/__init__.py \
	    stbt/config.py \
	    stbt/control.py \
	    stbt/core.py \
	    stbt/gst_hacks.py \
	    stbt/irnetbox.py \
	    stbt/logging.py \
	    stbt/pylint_plugin.py \
	    stbt/utils.py \
	    $(DESTDIR)$(libexecdir)/stbt/stbt
	$(INSTALL) -m 0644 defaults.conf $(DESTDIR)$(libexecdir)/stbt/stbt.conf
	$(INSTALL) -m 0755 \
	    stbt-batch.d/run \
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
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(man1dir)
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

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	sed -e '/\.\. image::/,/^$$/ d' |\
	rst2man > $@

# Ensure the docs for python functions are kept in sync with the code
README.rst: api-doc.sh stbt/__init__.py stbt/config.py
	STBT_CONFIG_FILE=stbt.conf ./api-doc.sh $@

clean:
	rm -f stbt.1 stbt.sh defaults.conf .stbt-prefix

PYTHON_FILES = $(shell (git ls-files '*.py' && \
           git grep --name-only -E '^\#!/usr/bin/(env python|python)') \
           | sort | uniq)

check: check-pylint check-nosetests check-integrationtests check-bashcompletion
check-nosetests: tests/ocr/menu.png
	# Workaround for https://github.com/nose-devs/nose/issues/49:
	cp stbt-control nosetest-issue-49-workaround-stbt-control.py && \
	nosetests --with-doctest -v --match "^test_" \
	    $(shell git ls-files '*.py' | grep -v tests/test.py) \
	    nosetest-issue-49-workaround-stbt-control.py && \
	rm nosetest-issue-49-workaround-stbt-control.py
check-integrationtests: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" && \
	grep -hEo '^test_[a-zA-Z0-9_]+' tests/test-*.sh |\
	$(parallel) tests/run-tests.sh -i
check-hardware: install-for-test
	export PATH="$$PWD/tests/test-install/bin:$$PATH" && \
	tests/run-tests.sh -i tests/hardware/test-hardware.sh
check-pylint:
	printf "%s\n" $(PYTHON_FILES) \
	| PYTHONPATH=$(PWD) $(parallel) extra/pylint.sh
check-bashcompletion:
	@echo Running stbt-completion unit tests
	@bash -c ' \
	    set -e; \
	    . ./stbt-completion; \
	    for t in `declare -F | awk "/_stbt_test_/ {print \\$$3}"`; do \
	        ($$t); \
	    done'

install-for-test:
	rm -rf tests/test-install && \
	unset MAKEFLAGS prefix exec_prefix bindir libexecdir datarootdir mandir \
	      man1dir sysconfdir && \
	make install prefix=$$PWD/tests/test-install

parallel := $(shell \
    parallel --version 2>/dev/null | grep -q GNU && \
    echo parallel --gnu -j +4 || echo xargs)

tests/ocr/menu.png : %.png : %.svg
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
	# Separate tar and gzip so we can pass "-n" for more deterministic tarball
	# generation
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
	etags *.py

# Debian Packaging

DPKG_OPTS?=

extra/debian/$(debian_base_release)~%/debian/changelog : extra/debian/changelog
	mkdir -p $(dir $@) && \
	sed -e "s/@RELEASE@/$(debian_base_release)~$*/g" \
	    -e "s/@DISTRIBUTION@/$*/g" \
	    $< >$@

extra/debian/$(debian_base_release)/debian/changelog : extra/debian/changelog
	mkdir -p $(dir $@) && \
	sed -e "s/@RELEASE@/$(debian_base_release)/g" \
	    -e "s/@DISTRIBUTION@/unstable/g" \
	    $< >$@

static_debian_files = \
	debian/compat \
	debian/control \
	debian/copyright \
	debian/rules \
	debian/source/format

extra/stb-tester_$(VERSION)-%.debian.tar.xz : \
		extra/debian/%/debian/changelog \
		$(patsubst %,extra/%,$(static_debian_files))
	$(MKTAR) -c -C extra -f $(patsubst %.tar.xz,%.tar,$@) $(static_debian_files) && \
	$(MKTAR) --append -C extra/debian/$*/ -f $(patsubst %.tar.xz,%.tar,$@) debian/changelog && \
	xz -f $(patsubst %.tar.xz,%.tar,$@)

debian-src-pkg/%/ : FORCE stb-tester-$(VERSION).tar.gz extra/stb-tester_$(VERSION)-%.debian.tar.xz
	rm -rf debian-src-pkg/$* debian-src-pkg/$*~ && \
	mkdir -p debian-src-pkg/$*~ && \
	srcdir=$$PWD && \
	tmpdir=$$(mktemp -d -t stb-tester-debian-pkg.XXXXXX) && \
	cd $$tmpdir && \
	cp $$srcdir/stb-tester-$(VERSION).tar.gz \
	   stb-tester_$(VERSION).orig.tar.gz && \
	cp $$srcdir/extra/stb-tester_$(VERSION)-$*.debian.tar.xz . && \
	tar -xzf stb-tester_$(VERSION).orig.tar.gz && \
	cd stb-tester-$(VERSION) && \
	tar -xJf ../stb-tester_$(VERSION)-$*.debian.tar.xz && \
	LINTIAN_PROFILE=ubuntu debuild -eLINTIAN_PROFILE -S $(DPKG_OPTS) && \
	cd .. && \
	mv stb-tester_$(VERSION)-$*.dsc stb-tester_$(VERSION)-$*_source.changes \
	   stb-tester_$(VERSION)-$*.debian.tar.xz stb-tester_$(VERSION).orig.tar.gz \
	   "$$srcdir/debian-src-pkg/$*~" && \
	cd "$$srcdir" && \
	rm -Rf "$$tmpdir" && \
	mv debian-src-pkg/$*~ debian-src-pkg/$*

debian_architecture=$(shell dpkg --print-architecture 2>/dev/null)
stb-tester_$(VERSION)-%_$(debian_architecture).deb : debian-src-pkg/%/
	tmpdir=$$(mktemp -dt stb-tester-deb-build.XXXXXX) && \
	dpkg-source -x debian-src-pkg/$*/stb-tester_$(VERSION)-$*.dsc $$tmpdir/source && \
	(cd "$$tmpdir/source" && \
	 DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -rfakeroot -b $(DPKG_OPTS)) && \
	mv "$$tmpdir/$@" . && \
	rm -rf "$$tmpdir"

deb : stb-tester_$(VERSION)-$(debian_base_release)_$(debian_architecture).deb

# Ubuntu PPA

DPUT_HOST?=ppa:stb-tester

ppa-publish-% : debian-src-pkg/%/ stb-tester-$(VERSION).tar.gz extra/fedora/stb-tester.spec
	dput $(DPUT_HOST) debian-src-pkg/$*/stb-tester_$(VERSION)-$*_source.changes

ppa-publish : $(patsubst %,ppa-publish-1~%,$(ubuntu_releases))

# Fedora Packaging

COPR_PROJECT?=stbt
COPR_PACKAGE?=stb-tester
rpm_topdir?=$(HOME)/rpmbuild
src_rpm=stb-tester-$(ESCAPED_VERSION)-1.fc20.src.rpm

srpm: $(src_rpm)

$(src_rpm): stb-tester-$(VERSION).tar.gz extra/fedora/stb-tester.spec
	@printf "\n*** Building Fedora src rpm ***\n"
	mkdir -p $(rpm_topdir)/SOURCES
	cp stb-tester-$(VERSION).tar.gz $(rpm_topdir)/SOURCES
	rpmbuild --define "_topdir $(rpm_topdir)" -bs extra/fedora/stb-tester.spec
	mv $(rpm_topdir)/SRPMS/$(src_rpm) .

# For copr-cli, generate API token from http://copr.fedoraproject.org/api/
# and paste into ~/.config/copr
copr-publish: $(src_rpm)
	@printf "\n*** Building rpm from src rpm to validate src rpm ***\n"
	yum-builddep -y $(src_rpm)
	rpmbuild --define "_topdir $(rpm_topdir)" -bb extra/fedora/stb-tester.spec
	@printf "\n*** Publishing src rpm to %s ***\n" \
	    https://github.com/drothlis/stb-tester-srpms
	rm -rf stb-tester-srpms
	git clone --depth 1 https://github.com/drothlis/stb-tester-srpms.git
	cp $(src_rpm) stb-tester-srpms
	cd stb-tester-srpms && \
	    git add $(src_rpm) && \
	    git commit -m "$(src_rpm)" && \
	    git push origin master
	@printf "\n*** Publishing package to COPR ***\n"
	copr-cli build stb-tester \
	    https://github.com/drothlis/stb-tester-srpms/raw/master/$(src_rpm)


.PHONY: all clean check deb dist doc install uninstall
.PHONY: check-bashcompletion check-hardware check-integrationtests
.PHONY: check-nosetests check-pylint install-for-test
.PHONY: copr-publish ppa-publish srpm
.PHONY: FORCE TAGS
