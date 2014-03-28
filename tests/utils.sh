set_config() {
    python - "$@" <<-EOF
	import sys, stbt
	section, name = sys.argv[1].split('.')
	stbt._set_config(section, name, sys.argv[2])
	EOF
}
