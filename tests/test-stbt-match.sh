# Run with ./run-tests.sh

test_that_stbt_match_finds_match() {
    stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue.png
}

test_that_stbt_match_doesnt_find_match() {
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-gamut.png
}

test_that_stbt_match_applies_confirm_threshold_parameter() {
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_method=absdiff confirm_threshold=0.16 &&
    stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_method=absdiff confirm_threshold=0.9
}

test_that_stbt_match_rejects_invalid_parameters() {
    ! stbt match \
        idontexist.png \
        "$testdir"/videotestsrc-redblue-with-dots.png &&
    cat log | grep -q "Invalid image 'idontexist.png'" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        idontexisteither.png &&
    cat log | grep -q "No such file: idontexisteither.png" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=0.9 \
        lahdee=dah &&
    cat log | grep -q "Invalid argument 'lahdee=dah'" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=five &&
    cat log | grep -q "Invalid argument 'confirm_threshold=five'"
}

test_that_stbt_match_is_an_alias_for_stbt_templatematch() {
    stbt templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue.png &&
    ! stbt templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-gamut.png
}
