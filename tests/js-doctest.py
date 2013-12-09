#!/usr/bin/python

import sys
import argparse
import re
import subprocess
from textwrap import dedent


def _iterate_tests(f):
    result = ""
    cmd = None
    prefix = None
    for line in f:
        if re.match(r'^\s*>>> ', line):
            if cmd is not None:
                yield (cmd, result)
            result = ""
            prefix, cmd = line.split('>>> ', 2)
        elif cmd is not None and line.startswith(prefix + '... '):
            cmd += line.split('... ', 2)[1]
        elif cmd is not None and line.startswith(prefix):
            result += line[len(prefix):]
        elif cmd is not None:
            yield (cmd, result)
            cmd = None
            result = ""
        else:
            # Is just a normal line
            pass
    if cmd is not None:
        yield (cmd, result)


def test_iterate_tests():
    from nose.tools import eq_
    from StringIO import StringIO
    examples = [
        ('', []),
        ('hello', []),
        ('multi\nline', []),
        ('   >>> command()', [
            ('command()', '')]),
        ('   >>> command()\n   result', [('command()\n', 'result')]),
        ('   >>> command()\n   ... hello\n   result',
            [('command()\nhello\n', 'result')]),
        ('   >>> multi\n   ... line\n   with multiline\n   result\nand '
         'other content\n', [('multi\nline\n', 'with multiline\nresult\n')]),
        ('   >>> two\n   >>> commands\n', [('two\n', ''), ('commands\n', '')]),
    ]
    for i, o in examples:
        eq_(list(_iterate_tests(StringIO(i))), o)


def indent(s):
    return "    " + "\n    ".join(s.split('\n'))


def main(argv):
    parser = argparse.ArgumentParser(
        description='Run doctests contained within in a javascript file.')
    parser.add_argument('infile')
    parser.add_argument('--verbose', '-v', action='count')

    args = parser.parse_args(argv[1:])

    count = 0
    errors = 0

    with open(args.infile, 'r') as f:
        for cmd, expected in _iterate_tests(f):
            count += 1
            if args.verbose >= 2:
                sys.stderr.write('Running test %s\n' % cmd)
            result = subprocess.check_output(
                ['seed', '-e', 'Seed.include("%s");\n%s' % (args.infile, cmd)])
            if result != expected:
                sys.stdout.write(dedent("""\
                =================================
                Doctest failure running command

                %s

                Expected output:

                %s

                Got:

                %s
                """) % (indent(cmd), indent(expected), indent(result)))
                errors += 1
    if args.verbose >= 1:
        sys.stderr.write("%i/%i tests passed\n" %
                         (count - errors, count))
    return errors

if __name__ == '__main__':
    sys.exit(main(sys.argv))
