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

INSTALL?=install
TAR ?= $(shell which gnutar >/dev/null 2>&1 && echo gnutar || echo tar)

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

.DELETE_ON_ERROR:


all: stbt stbt.1 defaults.conf

stbt: stbt.in .stbt-prefix VERSION
	sed -e 's,@VERSION@,$(VERSION),g' \
	    -e 's,@LIBEXECDIR@,$(libexecdir),g' \
	    -e 's,@SYSCONFDIR@,$(sysconfdir),g' $< > $@

defaults.conf: stbt.conf .stbt-prefix
	perl -lpe \
	    '/\[global\]/ && ($$_ .= "\n__system_config=$(sysconfdir)/stbt/stbt.conf")' \
	    $< > $@

install: stbt stbt.1 defaults.conf
	$(INSTALL) -m 0755 -d \
	    $(DESTDIR)$(bindir) \
	    $(DESTDIR)$(libexecdir)/stbt \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/static \
	    $(DESTDIR)$(libexecdir)/stbt/stbt-batch.d/templates \
	    $(DESTDIR)$(man1dir) \
	    $(DESTDIR)$(sysconfdir)/stbt \
	    $(DESTDIR)$(sysconfdir)/bash_completion.d
	$(INSTALL) -m 0755 stbt irnetbox-proxy $(DESTDIR)$(bindir)
	$(INSTALL) -m 0755 $(tools) $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 stbt.py stbt_pylint_plugin.py irnetbox.py \
	    $(DESTDIR)$(libexecdir)/stbt
	$(INSTALL) -m 0644 defaults.conf $(DESTDIR)$(libexecdir)/stbt/stbt.conf
	$(INSTALL) -m 0755 stbt-batch.d/run stbt-batch.d/report \
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
README.rst: stbt.py api-doc.sh
	STBT_CONFIG_FILE=stbt.conf ./api-doc.sh $@

clean:
	rm -f stbt.1 stbt defaults.conf .stbt-prefix

check: check-nosetests check-integrationtests check-pylint check-bashcompletion
check-nosetests:
	nosetests --with-doctest -v stbt.py irnetbox.py \
	    tests/test_*.py
check-integrationtests:
	grep -hEo '^test_[a-zA-Z0-9_]+' tests/test-*.sh |\
	$(parallel) tests/run-tests.sh
check-pylint:
	printf "%s\n" stbt.py stbt-run stbt-record stbt-config stbt-control \
	    stbt-templatematch \
	    stbt_pylint_plugin.py \
	    irnetbox.py irnetbox-proxy \
	    tests/test_*.py tests/fake-irnetbox stbt-batch.d/report.py \
	    stbt-batch.d/instaweb |\
	PYTHONPATH=$(PWD) $(parallel) extra/pylint.sh
check-bashcompletion:
	@echo Running stbt-completion unit tests
	@bash -c ' \
	    set -e; \
	    . ./stbt-completion; \
	    for t in `declare -F | awk "/_stbt_test_/ {print \\$$3}"`; do \
	        ($$t); \
	    done'

parallel := $(shell \
    parallel --version 2>/dev/null | grep -q GNU && \
    echo parallel --gnu || echo xargs)


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
	$(TAR) -c -z --transform='s,^,stb-tester-$(VERSION)/,' -f $@ $^


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

.PHONY: all clean check dist doc install uninstall
.PHONY: check-bashcompletion check-integrationtests check-nosetests check-pylint
.PHONY: FORCE TAGS
