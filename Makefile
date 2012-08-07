prefix?=/usr/local
sysconfdir?=$(prefix)/etc
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
	    -e 's,@PREFIX@,$(prefix),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' $< > $@

install: stbt stbt.1
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(prefix)/{bin,lib/stbt,share/man/man1} \
	    $(DESTDIR)$(sysconfdir)/{stbt,bash_completion.d}
	$(INSTALL) -m 0755 stbt $(DESTDIR)$(prefix)/bin
	$(INSTALL) -m 0755 stbt-record stbt-run $(DESTDIR)$(prefix)/lib/stbt
	$(INSTALL) -m 0644 stbt.py $(DESTDIR)$(prefix)/lib/stbt
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(prefix)/share/man/man1
	$(INSTALL) -m 0644 stbt.conf $(DESTDIR)$(sysconfdir)/stbt
	$(INSTALL) -m 0644 stbt-completion \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d/stbt

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

.DELETE_ON_ERROR:
