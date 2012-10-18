#!/bin/sh

# Generates documentation from python docstrings, and inserts it at the right
# place in the README file specified in $1.

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
    #  |  __dict__
    #  |      dictionary for instance variables ...

    pydoc stbt.$1 |
    awk -v f=$1 '
        NR <= 2   { next; }
        /^ \| *$/ { print ""; exit; }
        { sub("^stbt." f " = ", "");
          sub("class " f "\\(" f "\\)", "class " f);
          sub(/^ *$/, "");
          sub(/^ \|  /, "    ");
          print; }'
}

line() {
    grep -n "$1" $2 | awk -F: '{print $1}'
}

target=$1
first_line=$(( $(line "<start python docs>" $target) + 1 ))
last_line=$(( $(line "<end python docs>" $target) - 1 ))

{
    sed "$first_line q" $target
    doc press
    doc wait_for_match
    doc press_until_match
    doc wait_for_motion
    doc detect_match
    doc detect_motion
    doc MatchResult
    doc Position
    doc MotionResult
    sed -n "$last_line,\$ p" $target
} > $target.new &&
mv $target.new $target
