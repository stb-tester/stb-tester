#!/usr/bin/python3

"""
Copyright 2013 YouView TV Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

import argparse
import sys

import cv2

import _stbt.logging
import stbt_core as stbt


def error(s):
    sys.stderr.write("stbt match: error: %s\n" % s)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.prog = "stbt match"
    parser.description = """Run stbt's image-matching algorithm against a single
        frame (which you can capture using `stbt screenshot`)."""
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Dump image processing debug images to ./stbt-debug directory")
    parser.add_argument(
        "--all", action="store_true",
        help='Use "stbt.match_all" instead of "stbt.match"')
    parser.add_argument(
        "source_file", help="""The screenshot to compare against (you can
            capture it using 'stbt screenshot')""")
    parser.add_argument(
        "reference_file", help="The image to search for")
    parser.add_argument(
        "match_parameters", nargs="*",
        help="""Parameters for the image processing algorithm. See
            'MatchParameters' in the stbt API documentation. For example:
            'confirm_threshold=0.70')""")
    args = parser.parse_args(sys.argv[1:])
    _stbt.logging.init_logger()

    mp = {}
    try:
        for p in args.match_parameters:
            name, value = p.split("=")
            if name == "match_method":
                mp["match_method"] = value
            elif name == "match_threshold":
                mp["match_threshold"] = float(value)
            elif name == "confirm_method":
                mp["confirm_method"] = value
            elif name == "confirm_threshold":
                mp["confirm_threshold"] = float(value)
            elif name == "erode_passes":
                mp["erode_passes"] = int(value)
            else:
                raise Exception("Unknown match_parameter argument '%s'" % p)
    except Exception:  # pylint:disable=broad-except
        error("Invalid argument '%s'" % p)

    source_image = cv2.imread(args.source_file)
    if source_image is None:
        error("Invalid image '%s'" % args.source_file)

    with _stbt.logging.scoped_debug_level(2 if args.verbose else 1):
        match_found = False
        for result in stbt.match_all(
                args.reference_file, frame=source_image,
                match_parameters=stbt.MatchParameters(**mp)):
            print("%s: %s" % (
                "Match found" if result else "No match found. Closest match",
                result))
            if result:
                match_found = True
            if not args.all:
                break
        sys.exit(0 if match_found else 1)


if __name__ == "__main__":
    main()
