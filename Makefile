PREFIX?=/usr/local
INSTALL?=install

VERSION?=$(shell git describe --always --dirty)

all: stbt

stbt:
	sed s!@PREFIX@!$(PREFIX)!g stbt.in > stbt

install: stbt doc
	$(INSTALL) --mode 0755 -d $(DESTDIR)$(PREFIX)/{bin,lib/stbt}
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/bin stbt
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt-record stbt-run
	$(INSTALL) --mode 0644 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt.py
	$(INSTALL) --mode 0644 -t $(DESTDIR)$(PREFIX)/share/man/man1 stbt.1

doc: stbt.1

# Requires python-docutils
stbt.1: README.rst
	sed -e 's/^:Version: .*/:Version: $(VERSION)/' $< |\
	rst2man > $@

# Can only be run from within a git clone of stb-tester or VERSION wont be
# set correctly
dist: stb-tester-$(VERSION).tar.gz

stb-tester-$(VERSION).tar.gz:
	git archive HEAD --prefix stb-tester-$(VERSION)/ \
		-o stb-tester-$(VERSION).tar
	gzip stb-tester-$(VERSION).tar

.DELETE_ON_ERROR:
