trap 'echo -e "\nTotal: $i\nFailed: $f"; exit 2' sigint sigterm
date
i=0
f=0
while true; do
    if timeout 10 ./run-tests.sh test_clock_visualisation >&2; then
        echo -n .
    else
        echo -n F
        f=$((f + 1))
    fi
    i=$((i + 1))
done
