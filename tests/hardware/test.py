import stbt
import argparse
import sys


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-pipeline-restart", action="store_true")
    args = parser.parse_args(argv[1:])

    try:
        stbt.wait_for_match("../videotestsrc-redblue.png")
    except stbt.MatchTimeout:
        # This is ok.  In the future when we have more control of what is on
        # screen we can really check for matches.
        pass

    if args.test_pipeline_restart:
        # TODO: Automate this by using a Raspberry Pi to stimulate the capture
        #       hardware
        sys.stdout.write("Waiting for a long time for match to check pipeline "
                         "restart behaviour.  Please restart the set-top box "
                         "to check that stb-tester recovers")

        try:
            stbt.wait_for_match("../../tests/template.png", timeout_secs=60)
        except stbt.MatchTimeout:
            # This is ok.  In the future when we have more control of what is
            # on screen we can really check for matches.
            pass

if __name__ == '__main__':
    sys.exit(main(sys.argv))
