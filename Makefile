PREFIX?=/usr/local
INSTALL?=install


all: stbt

stbt:
	sed s!@PREFIX@!$(PREFIX)!g stbt.in > stbt

install: stbt
	$(INSTALL) --mode 0755 -d $(DESTDIR)$(PREFIX)/{bin,lib/stbt}
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/bin stbt
	$(INSTALL) --mode 0755 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt-record stbt-run
	$(INSTALL) --mode 0644 -t $(DESTDIR)$(PREFIX)/lib/stbt stbt.py

