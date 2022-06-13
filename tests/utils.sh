timeout="/usr/bin/timeout --verbose --signal=INT --kill-after=10"
timedout=124

fail() { echo "error: $*"; exit 1; }
skip() { echo "skipping: $*"; exit 77; }

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

assert_log() {
    if ! grep -qF "$1" "$scratchdir/log"; then
        fail "log doesn't contain text: $1"
    fi
}

killtree() {
    local parent=$1 child
    for child in $(ps -o ppid= -o pid= | awk "\$1==$parent {print \$2}"); do
        killtree $child
    done
    kill $parent
}

set_config() {
    PYTHONPATH=$srcdir $python - "$@" <<-EOF
	import sys, _stbt.config
	section, name = sys.argv[1].split('.')
	_stbt.config.set_config(section, name, sys.argv[2])
	EOF
}
