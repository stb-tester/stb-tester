PREFIX?=/usr/local
INSTALL?=install
TAR?=tar

generate_version := $(shell \
	git describe --always --dirty > VERSION.now 2>/dev/null && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)

VERSION?=$(shell cat VERSION)

all: stbt

stbt:
	sed s!@PREFIX@!$(PREFIX)!g stbt.in > stbt

install: stbt stbt.1
	$(INSTALL) -m 0755 -d $(DESTDIR)$(PREFIX)/{bin,lib/stbt,share/man/man1}
	$(INSTALL) -m 0755 stbt $(DESTDIR)$(PREFIX)/bin
	$(INSTALL) -m 0755 stbt-record stbt-run $(DESTDIR)$(PREFIX)/lib/stbt
	$(INSTALL) -m 0644 stbt.py $(DESTDIR)$(PREFIX)/lib/stbt
	$(INSTALL) -m 0644 stbt.1 $(DESTDIR)$(PREFIX)/share/man/man1

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	rst2man > $@

# Can only be run from within a git clone of stb-tester or VERSION wont be
# set correctly
dist: stb-tester-$(VERSION).tar.gz

stb-tester-$(VERSION).tar.gz: stbt.in stbt-record stbt-run stbt.py README.rst VERSION Makefile
	$(TAR) -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^

clean:
	rm -f stbt.1 stbt

check:
	python -m doctest -v stbt.py stbt-run stbt-record

.DELETE_ON_ERROR:
