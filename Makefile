# The default target of this Makefile is:
all:

prefix?=/usr/local
exec_prefix?=$(prefix)
bindir?=$(exec_prefix)/bin
libexecdir?=$(exec_prefix)/libexec
libdir?=$(exec_prefix)/lib
datarootdir?=$(prefix)/share
mandir?=$(datarootdir)/man
man1dir?=$(mandir)/man1
sysconfdir?=$(prefix)/etc

ifeq ($(prefix),$(HOME))
  plugindir?=$(HOME)/.gstreamer-0.10/plugins
else
  plugindir?=$(libdir)/gstreamer-0.10
endif

INSTALL?=install
TAR?=tar  # Must be GNU tar

dependencies = gstreamer-0.10
dependencies += gstreamer-base-0.10
dependencies += gstreamer-video-0.10
dependencies += opencv

# CFLAGS and LDFLAGS are for the user to override from the command line.
CFLAGS ?= -g -O2
extra_cflags = -fPIC '-DPACKAGE="stb-tester"' '-DVERSION="$(VERSION)"'
extra_cflags += $(shell pkg-config --cflags $(dependencies))
extra_ldflags = $(shell pkg-config --libs $(dependencies))

OBJS = gst/gst-stb-tester.o
OBJS += gst/gstmotiondetect.o
OBJS += gst/gsttemplatematch.o

# Generate version from 'git describe' when in git repository, and from
# VERSION file included in the dist tarball otherwise.
generate_version := $(shell \
	git describe --always --dirty > VERSION.now 2>/dev/null && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)
VERSION?=$(shell cat VERSION)

.DELETE_ON_ERROR:


all: stbt stbt.1 gst/libgst-stb-tester.so

stbt: stbt.in
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' $< > $@

install: stbt stbt.1 gst/libgst-stb-tester.so
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt \
	    $(DESTDIR)$(plugindir) \
	    $(DESTDIR)$(man1dir) \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d
	$(INSTALL) -m 0755 stbt $(DESTDIR)$(bindir)
	$(INSTALL) -m 0755 stbt-record stbt-run $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 stbt.py $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0755 gst/libgst-stb-tester.so $(DESTDIR)$(plugindir)
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(man1dir)
	$(INSTALL) -m 0644 stbt.conf $(DESTDIR)$(sysconfdir)/stbt
	$(INSTALL) -m 0644 stbt-completion \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	rst2man > $@

clean:
	rm -f stbt.1 stbt gst/*.o gst/libgst-stb-tester.so

check: check-nosetests check-integrationtests check-pep8 check-bashcompletion
check-nosetests:
	nosetests --with-doctest -v stbt.py
check-integrationtests:
	PATH="$$PWD:$$PATH" tests/run-tests.sh
check-pep8:
	pep8 stbt.py stbt-run stbt-record
check-bashcompletion:
	set -e; \
	. ./stbt-completion; \
	for t in `declare -F | awk '/_stbt_test_/ {print $$3}'`; do ($$t); done


# Can only be run from within a git clone of stb-tester or VERSION (and the
# list of files) won't be set correctly.
dist: stb-tester-$(VERSION).tar.gz

DIST = $(shell git ls-files)
DIST += VERSION

stb-tester-$(VERSION).tar.gz: $(DIST)
	$(TAR) -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^


# GStreamer plugin
gst/libgst-stb-tester.so: $(OBJS)
	$(CC) -shared -o $@ $^ $(extra_ldflags) $(LDFLAGS)

$(OBJS): %.o: %.c
	$(CC) -o $@ -c $(extra_cflags) $(CPPFLAGS) $(CFLAGS) $<
# Header dependencies:
gst/gstmotiondetect.o: gst/gstmotiondetect.h
gst/gsttemplatematch.o: gst/gsttemplatematch.h
