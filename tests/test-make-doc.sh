# Run with ./run-tests.sh

test_that_readme_default_templatematch_values_are_kept_up_to_date() {
    cat > "$scratchdir/readme" <<-'EOF'
	unmodified line
	    `match_method` (str) default: old value
	unmodified line
	EOF
    "$testdir/../api-doc.sh" "$scratchdir/readme"

    cat > "$scratchdir/expected" <<-'EOF'
	unmodified line
	    `match_method` (str) default: sqdiff-normed
	unmodified line
	EOF

    diff -u "$scratchdir/expected" "$scratchdir/readme"
}

test_that_readme_python_api_docs_are_kept_up_to_date() {
    cat > "$scratchdir/readme" <<-'EOF'
	unmodified line
	
	.. <start python docs>
	
	old lines
	
	.. <end python docs>
	
	unmodified line
	EOF
    "$testdir/../api-doc.sh" "$scratchdir/readme"

    cat > "$scratchdir/expected" <<-'EOF'
	unmodified line
	
	.. <start python docs>
	
	press(key)
	    Send the specified key-press to the system under test.
	
	.. <end python docs>
	
	unmodified line
	EOF

    diff -u <(head -6 "$scratchdir/expected") <(head -6 "$scratchdir/readme") &&
    diff -u <(tail -4 "$scratchdir/expected") <(tail -4 "$scratchdir/readme")
}
