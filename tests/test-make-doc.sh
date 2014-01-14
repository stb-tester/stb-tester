# Run with ./run-tests.sh

test_that_readme_default_templatematch_values_are_kept_up_to_date() {
    cat > readme <<-'EOF'
	unmodified line
	    `match_method` (str) default: old value
	unmodified line
	EOF
    "$srcdir"/api-doc.sh "$PWD"/readme

    cat > expected <<-'EOF'
	unmodified line
	    `match_method` (str) default: sqdiff-normed
	unmodified line
	EOF

    diff -u expected readme
}

test_that_readme_python_api_docs_are_kept_up_to_date() {
    cat > readme <<-'EOF'
	unmodified line
	
	.. <start python docs>
	
	old lines
	
	.. <end python docs>
	
	unmodified line
	EOF
    "$srcdir"/api-doc.sh "$PWD"/readme

    cat > expected <<-'EOF'
	unmodified line
	
	.. <start python docs>
	
	press(key, interpress_delay_secs=0.0)
	    Send the specified key-press to the system under test.
	
	.. <end python docs>
	
	unmodified line
	EOF

    diff -u <(head -6 expected) <(head -6 readme) &&
    diff -u <(tail -4 expected) <(tail -4 readme)
}
