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
TAR ?= $(shell which gnutar >/dev/null 2>&1 && echo gnutar || echo tar)

dependencies = gstreamer-0.10
dependencies += gstreamer-base-0.10
dependencies += gstreamer-video-0.10
dependencies += opencv

# CFLAGS and LDFLAGS are for the user to override from the command line.
CFLAGS ?= -g -O2 -Werror
extra_cflags = -fPIC '-DPACKAGE="stb-tester"'
extra_cflags += $(shell pkg-config --cflags $(dependencies))
extra_ldflags = $(shell pkg-config --libs $(dependencies))

OBJS = gst/gst-stb-tester.o
OBJS += gst/gstmotiondetect.o
OBJS += gst/gsttemplatematch.o

tools = stbt-run
tools += stbt-record
tools += stbt-config
tools += stbt-screenshot
tools += stbt-templatematch
tools += stbt-tv

# Allow building in a directory different to the source directory.
srcdir := $(dir $(lastword $(MAKEFILE_LIST)))
VPATH := $(srcdir)

# Generate version from 'git describe' when in git repository, and from
# VERSION file included in the dist tarball otherwise.
generate_version := $(shell \
	cd $(srcdir) && \
	GIT_DIR=.git git describe --always --dirty > VERSION.now 2>/dev/null && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)
VERSION?=$(shell cat $(srcdir)/VERSION)

.DELETE_ON_ERROR:


all: stbt stbt.1 defaults.conf gst/libgst-stb-tester.so

stbt: stbt.in .stbt-prefix VERSION
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' $< > $@

defaults.conf: stbt.conf .stbt-prefix
	perl -lpe \
	    '/\[global\]/ && ($$_ .= "\n__system_config=$(sysconfdir)/stbt/stbt.conf")' \
	    $< > $@

install: stbt stbt.1 defaults.conf gst/libgst-stb-tester.so
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt \
	    $(DESTDIR)$(plugindir) \
	    $(DESTDIR)$(man1dir) \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d
	$(INSTALL) -m 0755 stbt $(DESTDIR)$(bindir)
	$(INSTALL) -m 0755 $(tools) $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 stbt.py irnetbox.py $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 defaults.conf $(DESTDIR)$(libexecdir)/stbt/stbt.conf
	$(INSTALL) -m 0755 gst/libgst-stb-tester.so $(DESTDIR)$(plugindir)
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(man1dir)
	$(INSTALL) -m 0644 stbt.conf $(DESTDIR)$(sysconfdir)/stbt
	$(INSTALL) -m 0644 stbt-completion \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt

uninstall:
	rm -f $(DESTDIR)$(bindir)/stbt
	for t in $(tools); do rm -f $(DESTDIR)$(libexecdir)/stbt/$$t; done
	rm -f $(DESTDIR)$(libexecdir)/stbt/stbt.py
	rm -f $(DESTDIR)$(libexecdir)/stbt/irnetbox.py
	rm -f $(DESTDIR)$(libexecdir)/stbt/*.pyc
	rm -f $(DESTDIR)$(libexecdir)/stbt/stbt.conf
	rm -f $(DESTDIR)$(plugindir)/libgst-stb-tester.so
	rm -f $(DESTDIR)$(man1dir)/stbt.1
	rm -f $(DESTDIR)$(sysconfdir)/stbt/stbt.conf
	rm -f $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt
	-rmdir $(DESTDIR)$(libexecdir)/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/stbt
	-rmdir $(DESTDIR)$(sysconfdir)/bash_completion.d

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $(srcdir)/README.rst |\
	sed -e '/\.\. image::/,/^$$/ d' |\
	rst2man > $@

# Ensure the docs for python functions are kept in sync with the code
README.rst: stbt.py api-doc.sh
	$(srcdir)/api-doc.sh $@

clean:
	rm -f stbt.1 stbt defaults.conf gst/*.o gst/libgst-stb-tester.so \
	    .stbt-prefix .stbt-cflags .stbt-ldflags

check: check-nosetests check-integrationtests check-pylint check-bashcompletion
check-nosetests: stbt.py irnetbox.py
	nosetests --with-doctest -v $^
check-integrationtests: gst/libgst-stb-tester.so
	grep -hEo '^test_[a-zA-Z0-9_]+' $(srcdir)/tests/test-*.sh |\
	builddir=`pwd` $(parallel) $(srcdir)/tests/run-tests.sh
check-pylint: stbt.py irnetbox.py stbt-run stbt-record stbt-config
	printf "%s\n" $^ |\
	$(parallel) $(srcdir)/extra/pylint.sh
check-bashcompletion:
	@echo Running stbt-completion unit tests
	@bash -c ' \
	    set -e; \
	    . $(srcdir)/stbt-completion; \
	    for t in `declare -F | awk "/_stbt_test_/ {print \\$$3}"`; do \
	        ($$t); \
	    done'

parallel := $(shell \
    parallel --version 2>/dev/null | grep -q GNU && \
    echo parallel || echo xargs)


# Can only be run from within a git clone of stb-tester or VERSION (and the
# list of files) won't be set correctly.
dist: stb-tester-$(VERSION).tar.gz

DIST = $(shell cd $(srcdir) && git ls-files)
DIST += VERSION

stb-tester-$(VERSION).tar.gz: $(DIST)
	@$(TAR) --version 2>/dev/null | grep -q GNU || { \
	    printf 'Error: "make dist" requires GNU tar ' >&2; \
	    printf '(use "make dist TAR=gnutar").\n' >&2; \
	    exit 1; }
	$(TAR) -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^


# GStreamer plugin
gst/libgst-stb-tester.so: $(OBJS) .stbt-ldflags
	$(CC) -shared -o $@ $(OBJS) $(extra_ldflags) $(LDFLAGS)

$(OBJS): %.o: %.c .stbt-cflags
	@mkdir -p gst
	$(CC) -o $@ -c $(extra_cflags) $(CPPFLAGS) $(CFLAGS) \
	    '-DVERSION="$(VERSION)"' $<
# Header dependencies:
gst/gstmotiondetect.o: gst/gstmotiondetect.h
gst/gsttemplatematch.o: gst/gsttemplatematch.h
gst/gst-stb-tester.o: VERSION


# Force rebuild if installation directories or compilation flags change
sq = $(subst ','\'',$(1)) # function to escape single quotes (')
.stbt-prefix: flags = libexecdir=$(call sq,$(libexecdir)):\
                      sysconfdir=$(call sq,$(sysconfdir))
.stbt-cflags: flags = CC=$(call sq,$(CC)):\
                      extra_cflags=$(call sq,$(extra_cflags)):\
                      CPPFLAGS=$(call sq,$(CPPFLAGS)):\
                      CFLAGS=$(call sq,$(CFLAGS))
.stbt-ldflags: flags = extra_ldflags=$(call sq,$(extra_ldflags)):\
                       LDFLAGS=$(call sq,$(LDFLAGS))
.stbt-prefix .stbt-cflags .stbt-ldflags: FORCE
	@if [ '$(flags)' != "$$(cat $@ 2>/dev/null)" ]; then \
	    [ -f $@ ] && echo "*** new $@" >&2; \
	    echo '$(flags)' > $@; \
	fi


.PHONY: all clean check dist doc install uninstall
.PHONY: check-bashcompletion check-integrationtests check-nosetests check-pylint
.PHONY: FORCE
