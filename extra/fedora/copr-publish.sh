#!/bin/bash

# Publish the specified source rpm to the stb-tester repository on COPR (a
# PPA-style package builder & repository for Fedora) at
# http://copr.fedoraproject.org/coprs/stbt/stb-tester/
#
# Generate API token for copr-cli from http://copr.fedoraproject.org/api/
# and paste into ~/.config/copr

src_rpm=$1
set -x

[[ -n "$src_rpm" ]] &&
tmpdir=$(mktemp -d --tmpdir stb-tester-copr-publish.XXXXXX) &&
trap "rm -rf $tmpdir" EXIT &&
git clone --depth 1 git@github.com:stb-tester/stb-tester-srpms.git \
    $tmpdir/stb-tester-srpms &&
cp $src_rpm $tmpdir/stb-tester-srpms &&
git -C $tmpdir/stb-tester-srpms add $src_rpm &&
git -C $tmpdir/stb-tester-srpms commit -m "$src_rpm" &&
git -C $tmpdir/stb-tester-srpms push origin master &&
echo "Published srpm to https://github.com/stb-tester/stb-tester-srpms" &&
"$(dirname "$0")"/fedora-shell.sh -c "copr-cli build stb-tester \
    https://github.com/stb-tester/stb-tester-srpms/raw/master/$src_rpm" &&
echo "Kicked off copr build" &&
echo "See http://copr.fedoraproject.org/coprs/stbt/stb-tester/"
