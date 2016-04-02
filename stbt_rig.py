import argparse
import sys


def main(argv):
    parser = argparse.ArgumentParser()
    parser.parse_args(argv[1:])
    return 1

if __name__ == '__main__':
    sys.exit(main(sys.argv))
