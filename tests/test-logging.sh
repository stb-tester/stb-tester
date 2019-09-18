test_that_structlog_calls_are_logged() {
    cat > test.py <<-EOF
	import structlog
	log = structlog.get_logger("stbt")
	log.debug("Testing %s and {format} {thingies}", "positional",
	          format="keyword", thingies="substitutions")
	EOF
    stbt run -v test.py &&
    cat log | grep -q "stbt:DEBUG: Testing positional and keyword substitutions"
}

test_that_structlog_debug_isnt_logged_without_verbose_flag() {
    cat > stbt.conf <<-EOF
	[global]
	verbose = 0
	EOF
    export STBT_CONFIG_FILE=$(pwd)/stbt.conf:$STBT_CONFIG_FILE

    cat > test.py <<-EOF
	import structlog
	log = structlog.get_logger("stbt")
	log.debug("Testing")
	EOF
    stbt run test.py &&
    ! cat log | grep "Testing" &&

    stbt run -v test.py &&
    cat log | grep -q "Testing"
}

test_that_stdlib_logging_calls_are_logged() {
    cat > test.py <<-EOF
	import logging
	log = logging.getLogger()
	print("AAAAAAAAAAAAAAAA: %s" % log.getEffectiveLevel())
	logging.info("Testing %s %s", "stdlib", "logger",
	             extra={"ignored": "boohoo"})
	logging.debug("Testing stdlib debug")
	EOF
    stbt run -v test.py &&
    cat log | grep -q "root:INFO: Testing stdlib logger" &&
    ! cat log | grep "Testing stdlib debug"
}
