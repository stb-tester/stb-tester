#!/usr/bin/python

"""
"""

import argparse
import codecs
import os
import re
import StringIO
import sys
import traceback


def main(argv):
    parser = argparse.ArgumentParser()
    parser.parse_args(argv[1:])


def update_doctests(infilename, outfile):
    """
    Updates a file with doctests in it but no results to have "correct" results.
    """
    module = import_by_filename(infilename)
    if isinstance(outfile, str):
        outfile = open(outfile, 'w')
    with open(infilename, 'r') as infile:
        for line in infile:
            # pylint: disable=cell-var-from-loop
            m = re.match(r'\s*>>> (.*)\n', line)
            if m:
                cmd = m.group(1)
            else:
                outfile.write(("%s" % line).encode('utf-8'))
                continue

            if line.endswith(' # remove-if-false\n'):
                line = line.replace(' # remove-if-false\n', '\n')
                remove_if_false = True
            else:
                remove_if_false = False

            # At the end of this result[0] will either be "statement", "falsey",
            # "truey" or "exception":
            result = ["statement"]

            # This lets us know if anything was printed excluding the
            # value/exception produced by running the code.  It counts toward
            # our measure of interestingness
            did_print = [None]

            # doctest can't cope with printing unicode strings with unicode
            # codepoints in them.  This detects if we're going to fall into this
            # trap.
            would_unicode_fail = [False]

            oldstdout = sys.stdout
            io = StringIO.StringIO()
            real_write = io.write

            def io_write(text, *args, **kwargs):
                if isinstance(text, unicode):
                    try:
                        text = text.encode('ascii')
                    except UnicodeEncodeError:
                        would_unicode_fail[0] = True
                        text = text.encode('ascii', 'backslashreplace')
                return real_write(text, *args, **kwargs)

            io.write = io_write

            def displayhook(value):
                result[0] = "truthy" if bool(value) else "falsey"
                did_print[0] = (io.tell() != 0)
                if value is not None:
                    print repr(value)

            try:
                sys.stdout = io
                old_displayhook, sys.displayhook = sys.displayhook, displayhook
                exec compile(cmd, "<string>", "single") in module.__dict__  # pylint: disable=exec-used
                if did_print[0] is None:
                    did_print[0] = (io.tell() != 0)
            except Exception:  # pylint: disable=broad-except
                did_print[0] = (io.tell() != 0)
                result[0] = "exception"
                traceback.print_exc(0, io)
            finally:
                interesting = (did_print[0] or
                               result[0] in ["exception", "truthy"])
                sys.displayhook = old_displayhook
                sys.stdout = oldstdout
                if interesting or not remove_if_false:
                    if would_unicode_fail[0]:
                        line = re.sub(r"\n$", "  # doctest: +SKIP\n", line)
                    outfile.write("%s" % line)
                    io.seek(0)
                    for output_line in io:
                        if output_line.strip() == '':
                            outfile.write('    <BLANKLINE>\n')
                        else:
                            outfile.write('    ' + output_line)


def test_update_doctests():
    # We test that what we generate is what we expect.  make check-nosetests
    # will check that the generated doctest passes as a doctest itself.
    import subprocess
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile() as outfile:
        update_doctests(_find_file('tests/auto_selftest_bare.py'),
                        outfile.name)
        actual = outfile.read()
        with open(_find_file('tests/auto_selftest_expected.py')) as f:
            expected = f.read()
        if actual != expected:
            subprocess.call(
                ['diff', '-u', _find_file('tests/auto_selftest_expected.py'),
                 outfile.name])
        assert actual == expected


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


def import_by_filename(filename_):
    module_dir, module_file = os.path.split(filename_)
    module_name, module_ext = os.path.splitext(module_file)
    if module_ext != '.py':
        raise ImportError("Invalid module filename '%s'" % filename_)
    sys.path = [os.path.abspath(module_dir)] + sys.path
    return __import__(module_name)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
