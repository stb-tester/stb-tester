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

test_that_stbt_match_applies_match_method_parameter() {
    # sqdiff-normed gives incorrect result on all-black images
    ! stbt match \
        "$testdir"/black-full-frame.png "$testdir"/black-full-frame.png \
        match_method=sqdiff-normed || fail "sqdiff-normed should have failed"

    stbt match \
        "$testdir"/black-full-frame.png "$testdir"/black-full-frame.png \
        match_method=ccoeff-normed
}

test_that_stbt_match_applies_confirm_threshold_parameter() {
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        match_threshold=0.9 confirm_method=absdiff confirm_threshold=0.84 &&
    stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        match_threshold=0.9 confirm_method=absdiff confirm_threshold=0.1
}

test_that_stbt_match_rejects_invalid_parameters() {
    ! stbt match \
        idontexist.png \
        "$testdir"/videotestsrc-redblue-with-dots.png &&
    assert_log "Invalid image 'idontexist.png'" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        idontexisteither.png &&
    assert_log "No such file: 'idontexisteither.png'" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=0.1 \
        lahdee=dah &&
    assert_log "Invalid argument 'lahdee=dah'" &&
    ! stbt match \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue-with-dots.png \
        confirm_threshold=five &&
    assert_log "Invalid argument 'confirm_threshold=five'"
}

test_that_stbt_match_is_an_alias_for_stbt_templatematch() {
    stbt templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-redblue.png &&
    ! stbt templatematch \
        "$testdir"/videotestsrc-full-frame.png \
        "$testdir"/videotestsrc-gamut.png
}
