PREFIX?=/usr/local
INSTALL?=install

generate_version := $(shell \
	git describe --always --dirty > VERSION.now 2>/dev/null && \
	{ cmp VERSION.now VERSION 2>/dev/null || mv VERSION.now VERSION; }; \
	rm -f VERSION.now)

VERSION?=$(shell cat VERSION)

all: stbt

stbt:
	sed s!@PREFIX@!$(PREFIX)!g stbt.in > stbt

install: stbt stbt.1
	$(INSTALL) --mode 0755 -d $(DESTDIR)$(PREFIX)/{bin,lib/stbt,share/man/man1}
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/bin stbt
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt-record stbt-run
	$(INSTALL) --mode 0644 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt.py
	$(INSTALL) --mode 0644 -t $(DESTDIR)$(PREFIX)/share/man/man1 stbt.1

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst VERSION
	sed -e 's/@VERSION@/$(VERSION)/g' $< |\
	rst2man > $@

# Can only be run from within a git clone of stb-tester or VERSION wont be
# set correctly
dist: stb-tester-$(VERSION).tar.gz

stb-tester-$(VERSION).tar.gz: stbt.in stbt-record stbt-run stbt.py README.rst VERSION Makefile
	tar -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^

clean:
	rm -f stbt.1 stbt

.DELETE_ON_ERROR:
