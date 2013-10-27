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
        { sub("^stbt." f " = ", "");
          sub("class " f "\\(" f "\\)", "class " f);
          sub("class " f "\\(__builtin__.object\\)", "class " f);
          sub("exceptions.Exception", "Exception");
          sub("<stbt.MatchParameters instance>", "MatchParameters()");
          sub(/\*\*kwargs/, "\\*\\*kwargs");
          sub(/^ \|  /, "    ");
          sub(/^ *$/, "");
        }
        /^ *(Method resolution order:|Methods defined here:)$/ { exit; }
        { print; }'
}

# Keeps the python API section in sync with the docstrings in the source code.
substitute_python_docstrings() {
    export -f python_docstrings doc
    perl -lne '
        if (/<end python docs>/) { $deleting_old_docs=0;
                                   print `bash -c python_docstrings`; }
        if ($deleting_old_docs) { next; }
        if (/<start python docs>/) { $deleting_old_docs=1; }
        print;
    '
}
python_docstrings() {
    echo ""
    doc press
    doc wait_for_match
    doc wait_for_all_matches
    doc press_until_match
    doc wait_for_motion
    doc detect_match
    doc detect_motion
    doc frames
    doc save_frame
    doc get_frame
    doc draw_text
    doc load_image
    doc match_template
    doc get_config
    doc debug
    doc MatchParameters
    doc MatchResult
    doc Position
    doc MotionResult
    doc MatchTimeout
    doc MatchAllTimeout
    doc MotionTimeout
    doc NoVideo
    doc UITestFailure
    doc UITestError
}

# Prints sed commands to apply,
# to substitute default templatematch/motiondetect params from stbt.conf.
substitute_default_params() {
    local param value
    for param in \
        match.match_method \
        match.match_threshold \
        match.confirm_method \
        match.erode_passes \
        match.confirm_threshold \
        motion.noise_threshold \
        motion.consecutive_frames \
    ; do
        value=$(STBT_CONFIG_FILE=./stbt.conf ./stbt-config $param)
        # In:  `match_method` (str) default: <any value here>
        # Out: `match_method` (str) default: <value from stbt.conf>
        echo "s,^\( *\`${param#*.}\`.* default:\) .*,\1 $value,"
    done
}

cat $1 |
substitute_python_docstrings |
sed -f <(substitute_default_params) \
> $1.new &&
mv $1.new $1
