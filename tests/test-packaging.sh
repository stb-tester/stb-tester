# Run with ./run-tests.sh

test_importing_stbt_without_stbt_run() {
    cat > test.py <<-EOF
	import stbt, _stbt.opencv_shim as cv2
	assert stbt.match(
	    "$testdir/videotestsrc-redblue.png",
	    frame=cv2.imread("$testdir/videotestsrc-full-frame.png"))
	EOF
    python test.py
}

test_that_stbt_imports_the_installed_version() {
    cat > test.py <<-EOF
	import re, stbt
	print stbt.__file__
	print stbt._stbt.__file__
	def firstdir(path):
	    return re.match("/?[^/]+", path).group()
	assert firstdir(stbt.__file__) == firstdir(stbt._stbt.__file__)
	EOF
    python test.py || fail "Python imported the wrong _stbt"
    stbt run test.py || fail "stbt run imported the wrong _stbt"
}

test_that_stbt_imports_the_source_version() {
    (cd "$srcdir" && python <<-EOF) || fail "Python from srcdir imported the wrong _stbt"
	import stbt
	print stbt.__file__
	print stbt._stbt.__file__
	assert stbt.__file__.startswith("stbt/__init__.py")
	assert stbt._stbt.__file__.startswith("_stbt/__init__.py")
	EOF

    cat > test.py <<-EOF
	import re, stbt
	print stbt.__file__
	print stbt._stbt.__file__
	def firstdir(path):
	    return re.match("/?[^/]+", path).group()
	assert firstdir(stbt.__file__) == firstdir(stbt._stbt.__file__)
	EOF

    PYTHONPATH="$srcdir" python test.py ||
        fail 'Python with PYTHONPATH=$srcdir imported the wrong _stbt'

    "$srcdir"/stbt-run "$scratchdir"/test.py ||
        fail "stbt run imported the wrong _stbt"
}
