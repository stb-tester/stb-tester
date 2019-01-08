#!/bin/bash

#/ usage: build-source-package.sh <stb-tester version> <release>
#/
#/ <release> is "1" (for Debian unstable) or "1~trusty" (for an Ubuntu release).
#/
#/ Writes source package to "debian-packages" at the root of the stb-tester
#/ repo.

# A debian source package consists of three files:
#
# 1. The upstream tarball with .orig.tar.gz ending.
# 2. A description file with .dsc ending.
# 3. A tarball with .debian.tar.gz ending, containing any debian-specific
#    patches plus all the debian packaging files (compat, control, copyright,
#    rules, and source/format).

set -e

usage() { grep '^#/' "$0" | cut -c4-; }
[[ $# -eq 2 || $# -eq 3 ]] || { usage >&2; exit 1; }
die() { echo "$(basename $0): error: $*" >&2; exit 1; }

version=$1
release=$2
case "$release" in
    *~*) distribution=${release##*~};;
    *) distribution=unstable;;
esac

srcdir=$(dirname $0)/../..
builddir=$(mktemp -d --tmpdir stb-tester-build-debian-source-package.XXXXXX)
trap "rm -rf $builddir" EXIT

mktar() {
    tar --format=gnu --owner=root --group=root \
        --mtime="$(git show -s --format=%ci HEAD)" \
        "$@"
}

set -x

# .orig.tar.gz
rm -rf $builddir && mkdir -p $builddir
cp $srcdir/stb-tester-$version.tar.gz $builddir/stb-tester_$version.orig.tar.gz
tar -C $builddir -xzf $builddir/stb-tester_$version.orig.tar.gz

# Transfer debian control files to the build directory.
mkdir -p $builddir/stb-tester-$version/debian/source
cp $srcdir/extra/debian/compat \
    $srcdir/extra/debian/control \
    $srcdir/extra/debian/copyright \
    $srcdir/extra/debian/rules \
    $builddir/stb-tester-$version/debian
cp $srcdir/extra/debian/source/format $builddir/stb-tester-$version/debian/source
sed -e "s/@VERSION@/$version/g" \
    -e "s/@RELEASE@/$release/g" \
    -e "s/@DISTRIBUTION@/$distribution/g" \
    -e "s/@RFC_2822_DATE@/$(git -C "$srcdir" show -s --format=%aD HEAD)/g" \
    -e "s/@USER_NAME@/$(git -C "$srcdir" config user.name)/g" \
    -e "s/@USER_EMAIL@/$(git -C "$srcdir" config user.email)/g" \
    $srcdir/extra/debian/changelog.in \
    > $builddir/stb-tester-$version/debian/changelog

# .dsc & .debian.tar.gz (both created by debuild).
(cd $builddir/stb-tester-$version &&
 LINTIAN_PROFILE=ubuntu debuild -eLINTIAN_PROFILE -S -Zgzip $DPKG_OPTS)

# All done! Copy to stb-tester/debian-packages.
mkdir -p $srcdir/debian-packages
mv $builddir/stb-tester_$version.orig.tar.gz \
    $builddir/stb-tester_$version-$release.debian.tar.gz \
    $builddir/stb-tester_$version-$release.dsc \
    $builddir/stb-tester_$version-${release}_source.buildinfo \
    $builddir/stb-tester_$version-${release}_source.changes \
    $srcdir/debian-packages
