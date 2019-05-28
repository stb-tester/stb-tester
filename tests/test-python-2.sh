test_python_2_script() {
    [[ "$python_version" == "2.7" ]] || skip "Requires Python 2"
    cat > test.py <<-EOF
	print "hi"
	EOF
    stbt run -v test.py
}

test_python_2_function() {
    [[ "$python_version" == "2.7" ]] || skip "Requires Python 2"
    cat > test.py <<-EOF
	def test_print_statement():
	    print "hi"
	EOF
    stbt run -v test.py::test_print_statement
}

test_python_2_script_with_python3_compat() {
    cat > test.py <<-EOF
	from __future__ import print_function
	print "hi"
	EOF
    ! stbt run -v test.py || fail "stbt-run should fail"
    cat log | grep SyntaxError || fail "Didn't see 'SyntaxError'"
}

test_python_2_function_with_python3_compat() {
    cat > test.py <<-EOF
	from __future__ import print_function
	def test_print_statement():
	    print "hi"
	EOF
    ! stbt run -v test.py || fail "stbt-run should fail"
    cat log | grep SyntaxError || fail "Didn't see 'SyntaxError'"
}
