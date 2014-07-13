# Portable timeout command. Usage: timeout <secs> <command> [<args>...]
timeout() { "$testdir"/timeout.pl "$@"; }
timedout=142

fail() { echo "error: $*"; exit 1; }

assert() {
    local not ret
    [[ "$1" == '!' ]] && { not='!'; shift; } || not=
    "$@"
    ret=$?
    case "$not,$ret" in
        ,0) ;;
        ,*) fail "Command failed: $*";;
        !,0) fail "Expected command to fail: $*";;
        !,*) ;;
    esac
}

killtree() {
    local parent=$1 child
    for child in $(ps -o ppid= -o pid= | awk "\$1==$parent {print \$2}"); do
        killtree $child
    done
    kill $parent
}

set_config() {
    python - "$@" <<-EOF
	import sys, config
	section, name = sys.argv[1].split('.')
	config.set_config(section, name, sys.argv[2])
	EOF
}
