# Run with ./run-tests.sh

test_that_stbt_lint_passes_existing_images() {
    cat > test.py <<-EOF &&
	import stbt
	stbt.wait_for_match('$testdir/videotestsrc-redblue.png')
	EOF
    stbt lint --errors-only test.py
}

test_that_stbt_lint_fails_nonexistent_image() {
    cat > test.py <<-EOF &&
	import stbt
	stbt.wait_for_match('idontexist.png')
	EOF
    ! stbt lint --errors-only test.py
}

test_that_stbt_lint_ignores_generated_image_names() {
    cat > test.py <<-EOF &&
	import os
	import stbt
	var = 'idontexist'
	stbt.wait_for_match(var + '.png')
	stbt.wait_for_match('%s.png' % var)
	stbt.wait_for_match(os.path.join('directory', 'idontexist.png'))
	EOF
    stbt lint --errors-only test.py
}

test_that_stbt_lint_ignores_regular_expressions() {
    cat > test.py <<-EOF &&
	import re
	re.match(r'.*/(.*)\.png', '')
	EOF
    stbt lint --errors-only test.py
}

test_that_stbt_lint_ignores_images_created_by_the_stbt_script() {
    cat > test.py <<-EOF &&
	import cv2, stbt
	stbt.save_frame(stbt.get_frame(), 'i-dont-exist-yet.png')
	cv2.imwrite('neither-do-i.png', stbt.get_frame())
	EOF
    stbt lint --errors-only test.py
}

test_pylint_plugin_on_itself() {
    # It should work on arbitrary python files, so that you can just enable it
    # as a pylint plugin across your entire project, not just for stbt scripts.
    stbt lint --errors-only "$srcdir"/stbt_pylint_plugin.py
}

test_that_stbt_lint_checks_uses_of_stbt_return_values() {
    cat > test.py <<-EOF &&
	import stbt
	from stbt import match, press, wait_until
	
	def test_something():
	    assert wait_until(lambda: True)
	    some_var = wait_until(lambda: True)
	    if wait_until(lambda: True): pass
	    wait_until(lambda: True)
	    stbt.wait_until(lambda: True)
	    something_else_that_ends_in_wait_until()  # pylint:disable=E0602
	    assert match('$testdir/videotestsrc-redblue.png')
	    match('$testdir/videotestsrc-redblue.png')
	    press('KEY_OK')
	EOF
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E:  8, 4: "wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E:  9, 4: "stbt.wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 12, 4: "match" return value not used (missing "assert"?) (stbt-unused-return-value)
	EOF
    diff -u lint.expected lint.log
}

test_that_stbt_lint_checks_that_wait_until_argument_is_callable() {
    cat > test.py <<-EOF &&
	from stbt import is_screen_black, press, wait_until
	
	def return_a_function():
	    return lambda: True
	
	def test_something():
	    press('KEY_POWER')
	    assert wait_until(is_screen_black)
	    assert wait_until(is_screen_black())
	    assert wait_until(return_a_function())
	    assert wait_until(return_a_function()())
	    assert wait_until(lambda: True)
	    assert wait_until((lambda: True)())
	EOF
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E: 11,11: "wait_until" argument "return_a_function()()" isn't callable (stbt-wait-until-callable)
	E: 13,11: "wait_until" argument "lambda : True()" isn't callable (stbt-wait-until-callable)
	EOF
    diff -u lint.expected lint.log
}
