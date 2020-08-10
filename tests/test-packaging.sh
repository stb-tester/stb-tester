# Run with ./run-tests.sh

test_importing_stbt_without_stbt_run() {
    cat > test.py <<-EOF
	import stbt_core as stbt, cv2
	assert stbt.match(
	    "$testdir/videotestsrc-redblue.png",
	    frame=cv2.imread("$testdir/videotestsrc-full-frame.png"))
	EOF
    $python test.py
}

test_that_stbt_imports_the_installed_version() {
    cat > test.py <<-EOF
	import os, re, sys, stbt_core as stbt
	print(stbt.__file__)
	print(sys.modules[stbt.match.__module__].__file__)
	print(os.environ["PYTHONPATH"])
	prefix, _ = os.environ["PYTHONPATH"].split(":", 1)
	assert stbt.__file__.startswith(prefix)
	assert sys.modules[stbt.match.__module__].__file__.startswith(prefix)
	EOF
    $python test.py || fail "Python imported the wrong _stbt"
    stbt run test.py || fail "stbt run imported the wrong _stbt"
}

test_that_stbt_imports_the_source_version() {
    (cd "$srcdir" && $python <<-EOF) || fail "Python from srcdir imported the wrong _stbt"
	import re, sys, stbt_core as stbt
	print(stbt.__file__)
	print(sys.modules[stbt.match.__module__].__file__)
	print("$srcdir/")
	assert re.match(r"($srcdir/)?stbt_core/__init__.pyc?$", stbt.__file__)
	assert re.match(r"($srcdir/)?_stbt/match.pyc?$",
	                sys.modules[stbt.match.__module__].__file__)
	EOF

    cat > test.py <<-EOF
	import re, sys, stbt_core as stbt
	print(stbt.__file__)
	print(sys.modules[stbt.match.__module__].__file__)
	assert re.match(r"$srcdir/stbt_core/__init__.pyc?$", stbt.__file__)
	assert re.match(r"($srcdir/)?_stbt/match.pyc?$",
	                sys.modules[stbt.match.__module__].__file__)
	EOF

    PYTHONPATH="$srcdir" $python test.py ||
        fail 'Python with PYTHONPATH=$srcdir imported the wrong _stbt'

    $python "$srcdir"/stbt_run.py "$scratchdir"/test.py ||
        fail "stbt run imported the wrong _stbt"
}
