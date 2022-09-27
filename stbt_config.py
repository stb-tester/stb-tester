#!/usr/bin/python3

"""
Copyright 2013 YouView TV Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import argparse
import sys

from _stbt.config import _config_init, ConfigurationError, get_config


def error(s):
    sys.stderr.write("stbt config: error: %s\n" % s)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.prog = "stbt config"
    parser.description = """Prints the value of the specified key from the stbt
        configuration file. See 'configuration' in the stbt(1) man page."""
    parser.epilog = """Returns non-zero exit status if the specified key or
        section isn't found."""
    parser.add_argument(
        "--bash-completion", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "name", metavar="section.key",
        help="e.g. 'global.source_pipeline'")
    args = parser.parse_args(sys.argv[1:])

    if args.bash_completion:
        cfg = _config_init()
        for section in cfg.sections():
            for option in cfg.options(section):
                print("%s.%s" % (section, option))
        sys.exit(0)

    if args.name.rfind(".") == -1:
        error("'name' parameter must contain the section and key "
              "separated by a dot")

    section, key = args.name.rsplit(".", 1)

    try:
        print(get_config(section, key))
    except ConfigurationError as e:
        error(e)


if __name__ == "__main__":
    main()
