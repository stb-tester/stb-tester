# Run with ./run-tests.sh

test_that_stbt_templatematch_finds_match() {
    stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue.png
}

test_that_stbt_templatematch_doesnt_find_match() {
    ! stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-gamut.png
}

test_that_stbt_templatematch_applies_confirm_threshold_parameter() {
    ! stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png &&
    stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png confirm_threshold=0.9
}
