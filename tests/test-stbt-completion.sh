stbt_assert_get_prev() {
    [ "$_stbt_prev" = "$1" ] ||
        fail "_stbt_prev was '$_stbt_prev' (expected '$1')"
    [ "$_stbt_cur" = "$2" ] ||
        fail "_stbt_cur was '$_stbt_cur' (expected '$2')"
    echo _stbt_get_prev: ok
}

test_completion_get_prev() {
    cd "$srcdir" && . stbt-completion

    # User types "file.py"
    COMP_WORDS=(stbt run tests/test_functions.py); COMP_CWORD=2; _stbt_get_prev
    stbt_assert_get_prev "" tests/test_functions.py

    COMP_WORDS=(stbt run tests/test_functions.py : :); COMP_CWORD=4; _stbt_get_prev
    stbt_assert_get_prev tests/test_functions.py:: ""

    COMP_WORDS=(stbt run tests/test_functions.py ::); COMP_CWORD=3; _stbt_get_prev
    stbt_assert_get_prev tests/test_functions.py:: ""

    # User types "--control "
    COMP_WORDS=(stbt run --control ""); COMP_CWORD=3; _stbt_get_prev
    stbt_assert_get_prev --control= ""

    COMP_WORDS=(stbt run --control lir); COMP_CWORD=3; _stbt_get_prev
    stbt_assert_get_prev --control= lir

    COMP_WORDS=(stbt run --control lirc :); COMP_CWORD=4; _stbt_get_prev
    stbt_assert_get_prev --control=lirc: ""

    COMP_WORDS=(stbt run --control lirc : /var); COMP_CWORD=5; _stbt_get_prev
    stbt_assert_get_prev --control=lirc: /var

    COMP_WORDS=(stbt run --control lirc : :); COMP_CWORD=5; _stbt_get_prev
    stbt_assert_get_prev --control=lirc:: ""

    COMP_WORDS=(stbt run --control lirc ::); COMP_CWORD=4; _stbt_get_prev
    stbt_assert_get_prev --control=lirc:: ""

    COMP_WORDS=(stbt run --control lirc : : ""); COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev --control=lirc:: ""

    COMP_WORDS=(stbt run --control lirc : : abc); COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev --control=lirc:: abc

    # User types "--control="
    COMP_WORDS=(stbt run --control = ""); COMP_CWORD=4; _stbt_get_prev
    stbt_assert_get_prev --control= ""

    COMP_WORDS=(stbt run --control = lir); COMP_CWORD=4; _stbt_get_prev
    stbt_assert_get_prev --control= lir

    # _stbt_prev stops at most recent "--" flag
    COMP_WORDS=(stbt run -o test.py --control lir); COMP_CWORD=5; _stbt_get_prev
    stbt_assert_get_prev --control= lir

    COMP_WORDS=(stbt run -o test.py --control = lirc :); COMP_CWORD=7; _stbt_get_prev
    stbt_assert_get_prev --control=lirc: ""

    # --control=file://...
    COMP_WORDS=(stbt run --control = file : ""); COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev --control=file: ""

    COMP_WORDS=(stbt run --control = file : //); COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev --control=file: //

    COMP_WORDS=(stbt run --control = file : ///dev/stdin); COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev --control=file: ///dev/stdin

    # User types "match_method="
    COMP_WORDS=(stbt match frame.png template.png match_method = "");
    COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev match_method= ""

    COMP_WORDS=(stbt match frame.png template.png match_method = sqdiff);
    COMP_CWORD=6; _stbt_get_prev
    stbt_assert_get_prev match_method= sqdiff
}

test_completion_filename_possibly_with_test_functions() {
    . "$srcdir"/stbt-completion

    mkdir tests
    touch tests/test_success.py
    cat > tests/test_functions.py <<-EOF
	import os
	
	
	def test_that_this_test_is_run():
	    open("touched", "w").close()
	
	
	def test_that_does_nothing():
	    pass
	
	
	def test_that_asserts_the_impossible():
	    assert 1 + 1 == 3
	
	
	def test_that_chdirs():
	    os.chdir("/tmp")
	
	
	def test_that_dumps_core():
	    os.abort()
	EOF

    diff - <(_stbt_cur="tests/test_succ" \
                _stbt_filename_possibly_with_test_functions) <<-EOF ||
	tests/test_success.py 
	EOF
    fail "unexpected completions for file without 'test_' functions"

    diff - <(_stbt_cur="tests/test_func" \
                _stbt_filename_possibly_with_test_functions) <<-EOF ||
	tests/test_functions.py::test_that_this_test_is_run 
	tests/test_functions.py::test_that_does_nothing 
	tests/test_functions.py::test_that_asserts_the_impossible 
	tests/test_functions.py::test_that_chdirs 
	tests/test_functions.py::test_that_dumps_core 
	EOF
    fail "unexpected completions for file with 'test_' functions"

    diff <(printf "") \
         <(_stbt_cur="tests/idontexist" \
            _stbt_filename_possibly_with_test_functions) ||
    fail "unexpected completions for nonexistent file"

    diff - <(_stbt_prev="tests/test_functions.py::" _stbt_cur="test_that_" \
                _stbt_filename_possibly_with_test_functions) <<-EOF ||
	test_that_this_test_is_run 
	test_that_does_nothing 
	test_that_asserts_the_impossible 
	test_that_chdirs 
	test_that_dumps_core 
EOF
    fail "unexpected completions for file + ambiguous function prefix"

    diff - <(_stbt_prev="tests/test_functions.py::" _stbt_cur="test_that_this" \
                _stbt_filename_possibly_with_test_functions) <<-EOF ||
	test_that_this_test_is_run 
EOF
    fail "unexpected completions for file + unambiguous function prefix"
}

test_completion_filenames() {
    . "$srcdir/stbt-completion"
    mkdir a-dir
    touch a-file a-dir/one a-dir/two
    diff -u - <(_stbt_filenames "a-") <<-EOF ||
	a-file 
	a-dir/
	EOF
    fail "unexpected completions for files + directories"
}

test_completion_config_keys() {
    cd "$srcdir" && . stbt-completion
    diff -u \
        <(printf '%s\n' global.key1 global.key2 global.key3 global.key4 run.key5) \
        <(STBT_CONFIG_FILE="tests/completion-test.conf" _stbt_config_keys | grep 'key[0-9]') \
         ||
    fail "_stbt_config_keys unexpected output"
}
