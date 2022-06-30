#!/usr/bin/python3
"""Send remote control signals using the PC keyboard or from the command line.
"""

import argparse
import collections
import contextlib
import curses
import curses.ascii
import io
import math
import os
import sys
import threading
import time
from textwrap import dedent

import _stbt.control
from _stbt.config import ConfigurationError, get_config
from _stbt.logging import init_logger

SPECIAL_CHARS = {
    curses.ascii.SP: "Space",
    curses.ascii.NL: "Enter",
    curses.ascii.TAB: "Tab",
    curses.ascii.ESC: "Escape",
    curses.KEY_UP: "Up",
    curses.KEY_DOWN: "Down",
    curses.KEY_LEFT: "Left",
    curses.KEY_RIGHT: "Right",
    curses.KEY_BACKSPACE: "Backspace",
    curses.KEY_PPAGE: "PageUp",
    curses.KEY_NPAGE: "PageDown",
    curses.KEY_HOME: "Home",
    curses.KEY_END: "End",
    curses.KEY_IC: "Insert",
    curses.KEY_DC: "Delete",
}


def main(argv):
    args = argparser().parse_args(argv[1:])
    init_logger()

    if args.help_keymap:
        sys.exit(show_help_keymap())

    control = _stbt.control.uri_to_control(args.control, None)

    if args.remote_control_key:  # Send a single key and exit
        control.press(args.remote_control_key)
    else:  # Interactive
        for key in main_loop(args.control, args.keymap):
            control.press(key)


def argparser():
    parser = argparse.ArgumentParser()
    parser.prog = "stbt control"
    parser.description = ("Send remote control signals using the PC keyboard "
                          "or from the command line.")
    parser.add_argument(
        "--help-keymap", action='store_true', default=False,
        help="Show description of the keymap file format and exit.")
    parser.add_argument(
        "--keymap", default=default_keymap_file(),
        help="Load keymap from KEYMAP file; defaults to %(default)s. "
             "See `%(prog)s --help-keymap` for details.")
    parser.add_argument(
        "--control", default=get_config("global", "control"),
        help="Equivalent to the --control parameter of `stbt run`. "
             "See `man stbt` for available control types and configuration.")
    parser.add_argument(
        "remote_control_key", default=None, nargs='?',
        help=(
            "The name of a remote control key as in the control's config file "
            "(that is /etc/lirc/lircd.conf in case of a LIRC control device). "
            "Specifying this argument sends remote_control_key and exits. "
            "Omitting this argument brings up the printed keymap."))
    return parser


def show_help_keymap():
    """Keymap File

    A keymap file stores the mappings between keyboard keys and remote control
    keys. One line of the file stores one key mapping in the following format:

            <keyboard key> <remote control key> [<display name>]

    <keyboard key> is an ASCII character or one of the following keywords:

            Space, Enter, Tab, Escape, Up, Down, Left, Right, Backspace,
            PageUp, PageDown, Home, End, Insert, Delete

    Be careful that keywords are case sensitive.

    <remote control key> is the same as in the command line arguments. It
    cannot contain white spaces.

    <display name> is an optional alias for <remote control key> to show in the
    on-screen keymap; e.g. "m MENU Main Menu" displays "Main Menu" but sends
    the "MENU" remote control key when "m" is pressed on the PC keyboard. It
    may consist of multiple words but cannot be longer than 15 characters.

    Comments start with '//' (double slash) and last until the end of line.

    Example keymap:

            m       MENU    Main Menu
            Enter   OK
            c       CLOSE   Close     // Go back to live TV

    The keymap file to use can be specified by:

    1. Passing the filename of the keymap to the --keymap=<filename> command
       line argument.
    2. Or setting the configuration value `control.keymap` to the filename of
       the keymap file
    3. Copying it into $XDG_CONFIG_PATH/stbt/control.conf (defaults to
       $HOME/.config/stbt/control.conf).
    """
    print(globals()["show_help_keymap"].__doc__)


def main_loop(control_uri, keymap_file):
    try:
        keymap = load_keymap(open(keymap_file, "r", encoding="utf-8"))
    except IOError:
        error("Failed to load keymap file '%s'\n"
              "(see 'stbt control --help' for details of the keymap file)."
              % keymap_file)
    timer = None

    with terminal() as term:
        _, term_width = term.getmaxyx()
        printed_keymap = dedent("""\
            Keymap: {keymap_file}
            Control: {control_uri}

            {mapping}

            """).format(keymap_file=keymap_file[:term_width - len("Keymap:  ")],
                        control_uri=control_uri[:77] + (
                            control_uri[77:] and "..."),
                        mapping=keymap_string(keymap))
        if keymap_fits_terminal(term, printed_keymap):
            term.addstr(printed_keymap)
        else:
            raise EnvironmentError(
                "Unable to print keymap because the terminal is too small. "
                "Please resize the terminal window.")
        while True:  # Main loop
            keycode = term.getch()
            if keycode == ord('q'):  # 'q' for 'Quit' is pre-defined
                return

            control_key, _ = keymap.get(decoded(keycode), (None, None))
            if timer:
                timer.cancel()
                clear_last_command(term)
            if control_key:
                yield control_key
            term.addstr(str(control_key))
            timer = threading.Timer(1, clear_last_command, [term])
            timer.start()
            time.sleep(.2)
            curses.flushinp()


def clear_last_command(term):
    term.move(term.getyx()[0], 0)
    term.clrtoeol()


def keymap_fits_terminal(term, printed_keymap):
    term_y, term_x = term.getmaxyx()
    lines = printed_keymap.split("\n")
    return term_y > len(lines) and term_x > max(len(line) for line in lines)


@contextlib.contextmanager
def terminal():
    term = curses.initscr()
    curses.noecho()
    curses.cbreak()
    term.keypad(1)
    term.immedok(1)
    try:
        yield term
    finally:
        term.immedok(0)
        term.keypad(0)
        curses.nocbreak()
        curses.echo()
        curses.endwin()


def keymap_string(keymap):
    """
    >>> print(keymap_string({"m": ("MENU", "Main Menu")}).strip())
    q - <Quit>                        m - Main Menu
    """
    keylist = ["%15s - %-15s" % (kb_key, mapping[1])
               for kb_key, mapping in keymap.items()]
    keylist.insert(0, "%15s - %-15s" % ("q", "<Quit>"))
    middle = int(math.ceil(float(len(keylist)) / 2))
    rows = [
        "%s %s" % (
            keylist[i],
            keylist[middle + i] if middle + i < len(keylist) else "")
        for i in range(middle)]
    return "\n".join(rows)


def decoded(keycode):
    """
    >>> decoded(curses.KEY_BACKSPACE)
    'Backspace'
    >>> decoded(120)
    'x'
    """
    if keycode in SPECIAL_CHARS:
        return SPECIAL_CHARS[keycode]
    try:
        return chr(keycode)
    except ValueError:
        return None


def load_keymap(keymap_file):
    keymap = collections.OrderedDict()
    for line in keymap_file:
        items = line.split("//")[0].split()
        if len(items) < 2:
            continue
        if items[0] in keymap:
            raise ConfigurationError(
                "Multiple remote control keys assigned to keyboard key '%s' "
                "in the keymap file" % items[0])
        if len(items) == 2:
            keymap[items[0]] = (items[1],) * 2
        else:
            keymap[items[0]] = (items[1], " ".join(items[2:]))
        validate(items[0])
    return keymap


def test_load_keymap():
    keymap = load_keymap(io.StringIO(
        "Backspace  BACK  Go back to previous\n"  # Test display name
        "Enter  OK  //Move forward\n"))  # Test comments
    assert keymap["Backspace"] == ("BACK", "Go back to previous")
    assert keymap["Enter"] == ("OK", "OK")


def test_load_keymap_with_duplicated_key():
    try:
        load_keymap(io.StringIO("o OK\no OPEN\n"))
        assert False, "load_keymap should have thrown ConfigurationError"
    except ConfigurationError:
        pass


def validate(keyname):
    if keyname in SPECIAL_CHARS.values():
        return
    try:
        ord(keyname)
    except TypeError:
        raise ValueError("Invalid keyboard key in the keymap file: " + keyname)


def test_validate():
    try:
        validate("Invalid")
        assert False
    except ValueError:
        pass


def default_keymap_file():
    config_dir = os.environ.get(
        'XDG_CONFIG_HOME', '%s/.config' % os.environ['HOME'])
    return get_config("control", "keymap", "") or \
        os.path.join(config_dir, "stbt", "control.conf")


def error(s):
    sys.stderr.write("%s: error: %s\n" % (
        os.path.basename(sys.argv[0]), str(s)))
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
