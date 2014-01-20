#!/bin/bash

# Generates documentation from python docstrings, and inserts it at the right
# place in the README file specified in $1.

set -u

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
          sub(/^ \|  /, "    ");
          sub(/^ *$/, "");
        }
        /^ *(Method resolution order:|Methods defined here:)$/ { exit; }
        /^ *Data descriptors defined here:/ { skipping=1; next; }
        /^ *Data and other attributes defined here:/ {
                        skipping=0; in_attributes=1; next; }
        skipping { next; }
        in_attributes && /^ *$/ { next; }
        END { if(in_attributes) print ""; }
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
    doc press_until_match
    doc wait_for_motion
    doc detect_match
    doc detect_motion
    doc ocr
    doc OcrMode
    doc precondition
    doc frames
    doc save_frame
    doc get_frame
    doc is_screen_black
    doc draw_text
    doc get_config
    doc debug
    doc MatchParameters
    doc MatchResult
    doc Position
    doc Region
    doc MotionResult
    doc MatchTimeout
    doc MotionTimeout
    doc NoVideo
    doc PreconditionError
    doc UITestFailure
    doc UITestError
}

substitute_ocr_default_mode() {
    local mode=$(sed -n '/^class OcrMode/,/^[^ ]/ p' stbt.py | awk '/3/ {print $1}')
    sed "/^ocr(/ s/mode=3/mode=OcrMode.$mode/"
}

# stbt.precondition's `@contextmanager` decorator screws up the function
# signature seen by pydoc
substitute_precondition_signature() {
    local sig=$(sed -n '/^def precondition/ { s/:$//; s/^def //; p; }' stbt.py)
    sed "s/^precondition(.*/$sig/"
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
substitute_ocr_default_mode |
substitute_precondition_signature |
sed -f <(substitute_default_params) \
> $1.new &&
mv $1.new $1
