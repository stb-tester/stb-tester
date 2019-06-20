#!/bin/bash

#/ Send simultaneous commands to a network-controllable power switch infinitely.
#/
#/ Usage: power-switch-stress-test.sh <outlet-address> [<outlet-address> ...]
#/
#/ Device URI is read from the stbt config file; the address of the individual
#/ power outlet is replaced with the ones specified as command line arguments.
#/ Example: `power-switch-stress-test.sh 1-A{1..8}` sends requests to switch
#/ all 8 outlets of a PDUeX KWX unit simultaneously.

set -u

main() {
    [[ $# -ge 1 ]] || { grep '^#/' "$0" | cut -c4- >&2; exit 1; }

    outlets="$@"
    uri="$(stbt config global.power_outlet | sed -r 's/:[^:]+$//')"

    trap 'test_command on >/dev/null; exit' sigint sigterm

    while true; do
        test_command off
        test_command on
    done
}

test_command() {
    local cmd=$1

    echo -n "[$(date -R)] Sending '$cmd'... "
    send_concurrent_commands $cmd 2>&1 && echo "PASS" || echo "FAIL"
}

send_concurrent_commands() {
    local cmd=$1
    local pids=

    for outlet in $outlets; do
        stbt power --power-outlet="$uri:$outlet" $cmd &
        pids="$pids $!"
    done

    local ret=0
    for pid in $pids; do
        wait $pid || ret=1
    done
    return $ret
}

main "$@"
