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

test_that_stbt_templatematch_rejects_invalid_parameters() {
    ! stbt-templatematch \
        idontexist.png \
        "$testdir"/videotestsrc-redblue-with-dots.png &&
    cat log | grep -q "Invalid image 'idontexist.png'" &&
    ! stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        idontexisteither.png &&
    cat log | grep -q "Invalid image 'idontexisteither.png'" &&
    ! stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=0.9 \
        lahdee=dah &&
    cat log | grep -q "Invalid argument 'lahdee=dah'" &&
    ! stbt-templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=five &&
    cat log | grep -q "Invalid argument 'confirm_threshold=five'"
}
