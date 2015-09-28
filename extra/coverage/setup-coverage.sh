#!/bin/sh -e

srcdir="$(cd "$(dirname $0)"/../.. && pwd)"

mkdir -p $HOME/.local/lib/python2.7/site-packages

echo "import coverage
coverage.process_startup()
" >$HOME/.local/lib/python2.7/site-packages/usercustomize.py

cat >$srcdir/.coveragerc <<EOF
[run]
source =
    $srcdir/
include =
    $srcdir
    $srcdir/*.py
    $srcdir/*/*.py
parallel = True
data_file = $srcdir/.coverage

[paths]
source =
    $srcdir
    $srcdir/tests/test-install/libexec/stbt
EOF
