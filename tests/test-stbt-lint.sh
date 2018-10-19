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
	from os.path import join
	var = 'idontexist'
	stbt.wait_for_match(var + '.png')
	stbt.wait_for_match('%s.png' % var)
	stbt.wait_for_match(os.path.join('directory', 'idontexist.png'))
	stbt.wait_for_match(join('directory', 'idontexist.png'))
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
	
	from cv2 import imwrite
	from stbt import save_frame
	save_frame(stbt.get_frame(), 'i-dont-exist-yet.png')
	imwrite('neither-do-i.png', stbt.get_frame())
	EOF
    stbt lint --errors-only --extension-pkg-whitelist=cv2 test.py
}

test_that_stbt_lint_ignores_multiline_image_name() {
    cat > test.py <<-EOF &&
	import subprocess
	subprocess.check_call("""set -e
	    tvservice -e "CEA 16"  # 1080p60
	    sudo fbi -T 1 -noverbose original.png
	    sudo fbi -T 2 -noverbose original.png""")
	EOF
    stbt lint --errors-only test.py
}

test_that_stbt_lint_ignores_image_urls() {
    cat > test.py <<-EOF &&
	import urllib2
	urllib2.urlopen("http://example.com/image.png")
	EOF
    stbt lint --errors-only test.py
}

test_that_stbt_lint_reports_uncommitted_images() {
    mkdir -p repo/tests/images
    touch repo/tests/images/reference.png
    cat > repo/tests/test.py <<-EOF
	import stbt
	assert stbt.match("images/reference.png")
	EOF
    cd repo
    stbt lint --errors-only tests/test.py ||
        fail "checker should be disabled because we're not in a git repo"

    git init .
    stbt lint --errors-only tests/test.py &> lint.log
    cat > lint.expected <<-EOF
	************* Module test
	E:  2,18: Image "tests/images/reference.png" not committed to git (stbt-uncommitted-image)
	EOF
    diff -u lint.expected lint.log || fail "(see diff above)"

    (cd tests && stbt lint --errors-only test.py) &> lint.log
    cat > lint.expected <<-EOF
	************* Module test
	E:  2,18: Image "images/reference.png" not committed to git (stbt-uncommitted-image)
	EOF
    diff -u lint.expected lint.log || fail "(see diff above)"

    git add tests/images/reference.png
    stbt lint --errors-only tests/test.py || fail "stbt-lint should succeed"

    (cd tests && stbt lint --errors-only test.py) ||
        fail "stbt-lint should succeed from subdirectory too"
}

test_pylint_plugin_on_itself() {
    # It should work on arbitrary python files, so that you can just enable it
    # as a pylint plugin across your entire project, not just for stbt scripts.
    stbt lint --errors-only "$srcdir"/_stbt/pylint_plugin.py
}

test_that_stbt_lint_checks_uses_of_stbt_return_values() {
    cat > test.py <<-EOF &&
	import re, stbt
	from stbt import (is_screen_black, match, match_text, ocr, press,
	                  press_and_wait, wait_until)
	
	def test_something():
	    assert wait_until(lambda: True)
	    some_var = wait_until(lambda: True)
	    if wait_until(lambda: True): pass
	    wait_until(lambda: True)
	    stbt.wait_until(lambda: True)
	    something_else_that_ends_in_wait_until()  # pylint:disable=undefined-variable
	    assert match('$testdir/videotestsrc-redblue.png')
	    match('$testdir/videotestsrc-redblue.png')
	    re.match('foo', 'bah')
	    press('KEY_OK')
	    is_screen_black()
	    match_text('hello')
	    ocr()
	    press_and_wait("KEY_DOWN")
	    stbt.press_and_wait("KEY_DOWN")
	    assert press_and_wait("KEY_DOWN")
	    assert stbt.press_and_wait("KEY_DOWN")
	EOF
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E:  9, 4: "wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 10, 4: "stbt.wait_until" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 13, 4: "match" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 16, 4: "is_screen_black" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 17, 4: "match_text" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 18, 4: "ocr" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 19, 4: "press_and_wait" return value not used (missing "assert"?) (stbt-unused-return-value)
	E: 20, 4: "stbt.press_and_wait" return value not used (missing "assert"?) (stbt-unused-return-value)
	EOF
    diff -u lint.expected lint.log
}

test_that_stbt_lint_checks_that_wait_until_argument_is_callable() {
    cat > test.py <<-EOF &&
	import functools
	from functools import partial
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
	    assert wait_until(functools.partial(lambda x: True, x=3))
	    assert wait_until(functools.partial(lambda x: True, x=3)())
	    assert wait_until(partial(lambda x: True, x=3))  # Pylint can't infer functools.partial. pylint:disable=stbt-wait-until-callable
	    assert wait_until(partial(lambda x: True, x=3)())
	EOF
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E: 11,11: "wait_until" argument "is_screen_black()" isn't callable (stbt-wait-until-callable)
	E: 13,11: "wait_until" argument "return_a_function()()" isn't callable (stbt-wait-until-callable)
	E: 15,11: "wait_until" argument "lambda : True()" isn't callable (stbt-wait-until-callable)
	E: 17,11: "wait_until" argument "functools.partial(lambda x: True, x=3)()" isn't callable (stbt-wait-until-callable)
	E: 19,11: "wait_until" argument "partial(lambda x: True, x=3)()" isn't callable (stbt-wait-until-callable)
	EOF
    diff -u lint.expected lint.log
}

test_that_stbt_lint_checks_frame_parameter_in_frameobject_methods() {
    cat > test.py <<-EOF
	from stbt import FrameObject, match, match_text, ocr, is_screen_black
	
	def find_boxes(frame=None):
	    pass
	
	class ModalDialog(FrameObject):
	    @property
	    def is_visible(self):
	        return bool(find_boxes())
	
	class ErrorDialog(ModalDialog):
	    @property
	    def is_visible(self):
	        return bool(
	            match("videotestsrc-redblue.png") and
	            match_text("Error") and
	            not is_screen_black())
	
	    @property
	    def text(self):
	        return ocr()
	
	class Good(FrameObject):
	    @property
	    def is_visible(self):
	        return bool(find_boxes(self._frame))
	
	    @property
	    def property1(self):
	        return bool(match("videotestsrc-redblue.png", self._frame))
	
	    @property
	    def property2(self):
	        return bool(match("videotestsrc-redblue.png", frame=self._frame))
	
	    def not_a_property(self):
	        return bool(match("videotestsrc-redblue.png"))
	
	def normal_test():
	    assert match("videotestsrc-redblue.png")
	EOF
    cp "$testdir/videotestsrc-redblue.png" .
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E:  9,20: "find_boxes()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 15,12: "match('videotestsrc-redblue.png')" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 16,12: "match_text('Error')" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 17,16: "is_screen_black()" missing "frame" argument (stbt-frame-object-missing-frame)
	E: 21,15: "ocr()" missing "frame" argument (stbt-frame-object-missing-frame)
	EOF
    diff -u lint.expected lint.log
}

test_that_stbt_lint_ignores_astroid_inference_exceptions() {
    cat > test.py <<-EOF
	import stbt
	assert stbt.wait_until(InfoPage)
	EOF
    stbt lint --errors-only test.py > lint.log

    cat > lint.expected <<-'EOF'
	************* Module test
	E:  2, 7: "wait_until" argument "InfoPage" isn't callable (stbt-wait-until-callable)
	E:  2,23: Undefined variable 'InfoPage' (undefined-variable)
	EOF
    diff -u lint.expected lint.log
}
