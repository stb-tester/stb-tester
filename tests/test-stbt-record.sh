# Run with ./run-tests.sh

test_record() {
    (
        cd "$scratchdir"
        stbt-record -v -o test.py --control-recorder=file://<(
            sleep 1; echo 15; sleep 1; echo 10; sleep 1; echo 0; sleep 1;)
    )
    sed -e 's/0000-15-complete.png/videotestsrc-gamut.png/' \
        -e 's/0001-10-complete.png/videotestsrc-checkers-8.png/' \
        -e 's/0002-0-complete.png/videotestsrc-redblue.png/' \
        "$scratchdir/test.py" > "$scratchdir/test.with-cropped-images.py"
    mv "$scratchdir/test.with-cropped-images.py" "$scratchdir/test.py"
    rm "$scratchdir/"{0000,0001,0002}-*-complete.png

    stbt-run -v "$scratchdir/test.py"
}
