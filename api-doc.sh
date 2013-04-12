#!/bin/bash

# Generates documentation from python docstrings, and inserts it at the right
# place in the README file specified in $1.

cd "$(dirname "$0")"

doc() {
    # $ pydoc stbt.press
    # Help on function press in stbt:
    #
    # stbt.press = press(key)
    #     Send the specified key-press to the system under test.
    #     
    #     The mechanism used to send the key-press depends on ...

    # $ pydoc stbt.Position
    # Help on class Position in stbt:
    #
    # stbt.Position = class Position(Position)
    #  |  `x` and `y`: Integer coordinates from the top left corner.
    #  |  
    #  |  Method resolution order:
    #  ...

    # $ pydoc stbt.UITestError
    # stbt.UITestError = class UITestError(exceptions.Exception)
    #  |  The test script had an unrecoverable error.
    #  |  
    #  |  Method resolution order:
    #  ...

    pydoc stbt.$1 |
    awk -v f=$1 '
        NR <= 2   { next; }
        /^ \| *$/ { print ""; exit; }
        { sub("^stbt." f " = ", "");
          sub("class " f "\\(" f "\\)", "class " f);
          sub("exceptions.Exception", "Exception");
          sub(/\*\*kwargs/, "\\*\\*kwargs");
          sub(/^ *$/, "");
          sub(/^ \|  /, "    ");
          print; }'
}

# Keeps the python API section in sync with the docstrings in the source code.
python_docstrings() {
    local input=$1
    local first_line=$(( $(line "<start python docs>" $input) + 1 ))
    local last_line=$(( $(line "<end python docs>" $input) - 1 ))

    sed "$first_line q" $input
    doc press
    doc wait_for_match
    doc press_until_match
    doc wait_for_motion
    doc detect_match
    doc detect_motion
    doc save_frame
    doc get_frame
    doc get_config
    doc debug
    doc MatchResult
    doc Position
    doc MotionResult
    doc MatchTimeout
    doc MotionTimeout
    doc UITestFailure
    doc UITestError
    sed -n "$last_line,\$ p" $input
}
line() {
    grep -n "$1" $2 | awk -F: '{print $1}'
}

# Prints sed commands to apply,
# to substitute default templatematch params from stbt.conf.
templatematch_params() {
    local param value
    for param in \
        match_method \
        match_threshold \
        confirm_method \
        erode_passes \
        confirm_threshold \
    ; do
        value=$(STBT_CONFIG_FILE=./stbt.conf ./stbt-config $param)
        # In:  `match_method` (str) default: <any value here>
        # Out: `match_method` (str) default: <value from stbt.conf>
        echo "s,^\(\`$param\`.* default:\) .*,\1 $value,"
    done
}
get() {
    STBT_CONFIG_FILE="$(dirname "$0")/stbt.conf" ./stbt-config $1
}

tmp=$1.$$

python_docstrings $1 |
sed -f <(templatematch_params) > $tmp
mv $tmp $1
