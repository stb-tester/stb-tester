PREFIX?=/usr/local
SYSCONFDIR?=$(PREFIX)/etc
INSTALL?=install
TAR?=tar  # Must be GNU tar

# Generate version from 'git describe' when in git repository, and from
# VERSION file included in the dist tarball otherwise.
generate_version := $(shell \
	git describe --always --dirty > VERSION.now 2>/dev/null && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)
VERSION?=$(shell cat VERSION)

all: stbt stbt.1

stbt: stbt.in
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@PREFIX@,$(PREFIX),g' \
	    -e 's,@SYSCONFDIR@,$(SYSCONFDIR),g' $< > $@

install: stbt stbt.1
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(PREFIX)/{bin,lib/stbt,share/man/man1} \
	    $(DESTDIR)$(SYSCONFDIR)/stbt
	$(INSTALL) -m 0755 stbt $(DESTDIR)$(PREFIX)/bin
	$(INSTALL) -m 0755 stbt-record stbt-run $(DESTDIR)$(PREFIX)/lib/stbt
	$(INSTALL) -m 0644 stbt.py $(DESTDIR)$(PREFIX)/lib/stbt
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(PREFIX)/share/man/man1
	$(INSTALL) -m 0644 stbt.conf $(DESTDIR)$(SYSCONFDIR)/stbt

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	rst2man > $@

# Can only be run from within a git clone of stb-tester or VERSION wont be
# set correctly
dist: stb-tester-$(VERSION).tar.gz

stb-tester-$(VERSION).tar.gz: stbt-record stbt-run stbt.conf stbt.in stbt.py \
                              LICENSE Makefile README.rst VERSION
	$(TAR) -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^

clean:
	rm -f stbt.1 stbt

check:
	nosetests --with-doctest -v stbt.py
	PATH="$$PWD:$$PATH" tests/run-tests.sh
	pep8 stbt.py stbt-run stbt-record

.DELETE_ON_ERROR:
