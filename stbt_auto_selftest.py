#!/usr/bin/env python

"""
``stbt auto-selftest`` captures the behaviour of Frame Objects (and other
helper functions that operate on a video-frame) by generating doctests. When
you change these helper functions, the generated doctests help to ensure that
they still behave correctly.

Usage:

    stbt auto-selftest generate
    stbt auto-selftest validate

``stbt auto-selftests generate`` generates a doctest for every `FrameObject` in
your test-pack against any screenshots stored in ``selftest/screenshots``. This
results in a set of python files under ``selftest/auto_selftest`` which can be
inspected by (human) eye and validated either with ``python -m doctest
<filename>`` or more commonly with ``stbt auto-selftests validate``.

**auto-selftest checklist**

1. Take screenshots of the device-under-test and put them in the
   ``selftest/auto_selftest`` directory of your test-pack.
2. Run ``stbt auto-selftest generate`` after every change to your Frame
   Objects, or after adding a new screenshot.
3. View the effect of your changes with ``git diff``.
4. Commit the changes to your auto-selftests along with your changes to the
   Frame Objects.
5. Run ``stbt auto-selftests validate`` on every change from your Continuous
   Integration system.

Using auto-selftests makes it much easier to create, update and modify Frame
Objects. If you find a screen where your Frame Object doesn't behave properly,
add that screenshot to your selftest corpus, and fix the Frame Object; the
auto-selftests will check that you haven't introduced a regression in the Frame
Object's behaviour against the other screenshots.

For more information and for more advanced usage see the example test file
(``tests/example.py``), the accompanying screenshots
(``selftest/screenshots``), and the generated doctest
(``selftest/auto_selftest/tests/example_selftest.py``) under
<https://github.com/stb-tester/stb-tester/tree/master/tests/auto-selftest-example-test-pack/>.

For more information on the background behind auto-selftests see
`Improve black-box testing agility: automatic self-regression tests
<https://stb-tester.com/blog/2015/09/24/automatic-self-regression-tests>`_.
"""

import argparse
import cStringIO
import errno
import fnmatch
import multiprocessing
import os
import re
import shutil
import signal
import StringIO
import sys
import tempfile
import time
import traceback
from collections import namedtuple
from textwrap import dedent, wrap

from _stbt.imgproc_cache import cache
from _stbt.utils import mkdir_p

SCREENSHOTS_ROOT = "selftest/screenshots"


def main(argv):
    parser = argparse.ArgumentParser(
        prog="stbt auto-selftest",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        'generate', help="Regenerate auto-selftests from screenshots")
    subparsers.add_parser('validate', help='Run (and check) the auto-selftests')

    cmdline_args = parser.parse_args(argv[1:])

    root = _find_test_pack_root()
    if root is None:
        sys.stderr.write(
            "This command must be run within a test pack.  Couldn't find a "
            ".stbt.conf in this or any parent directory.\n")
        return 1

    os.chdir(root)

    if cmdline_args.command == 'generate':
        generate()
    elif cmdline_args.command == 'validate':
        return validate()
    else:
        assert False


def generate():
    tmpdir = generate_into_tmpdir()
    try:
        target = "%s/selftest/auto_selftest" % os.curdir
        if os.path.exists(target):
            shutil.rmtree(target)
        os.rename(tmpdir, target)
    except:
        shutil.rmtree(tmpdir)
        raise


def validate():
    import filecmp
    tmpdir = generate_into_tmpdir()
    try:
        orig_files = _recursive_glob(
            '*.py', "%s/selftest/auto_selftest" % os.curdir)
        new_files = _recursive_glob('*.py', tmpdir)
        if orig_files != new_files:
            return 1
        _, mismatch, errors = filecmp.cmpfiles(
            tmpdir, "%s/selftest/auto_selftest" % os.curdir, orig_files)
        if mismatch or errors:
            return 1
        else:
            return 0
    finally:
        shutil.rmtree(tmpdir)


def is_valid_python_identifier(x):
    return bool(re.match('^[a-zA-Z_][a-zA-Z0-9_]*$', x))


def prune_empty_directories(dir_):
    for root, _dirs, files in os.walk(dir_, topdown=False):
        if len(files) == 0 and root != dir_:
            try:
                os.rmdir(root)
            except OSError as e:
                if e.errno not in [errno.EEXIST, errno.ENOTEMPTY]:
                    raise


def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def iterate_with_progress(sequence, width=20, stream=sys.stderr):
    ANSI_ERASE_LINE = '\033[K'
    stream.write('\n')
    total = len(sequence)
    for n, v in enumerate(sequence):
        if n == total:
            break
        progress = (n * width) // total
        stream.write(
            ANSI_ERASE_LINE + '[%s] %8d / %d - Processing %s\r' % (
                '#' * progress + ' ' * (width - progress), n, total, str(v)))
        yield v
    stream.write('\n')


def generate_into_tmpdir():
    start_time = time.time()

    selftest_dir = "%s/selftest" % os.curdir
    mkdir_p(selftest_dir)
    # We use this process pool for sandboxing rather than concurrency:
    pool = multiprocessing.Pool(
        processes=1, maxtasksperchild=1, initializer=init_worker)
    tmpdir = tempfile.mkdtemp(dir=selftest_dir, prefix="auto_selftest")
    try:
        filenames = []
        for module_filename in _recursive_glob('*.py'):
            if module_filename.startswith('selftest'):
                continue
            if not is_valid_python_identifier(
                    os.path.basename(module_filename)[:-3]):
                continue
            filenames.append(module_filename)

        perf_log = []
        test_file_count = 0
        for module_filename in iterate_with_progress(filenames):
            outname = os.path.join(
                tmpdir, re.sub('.py$', '_selftest.py', module_filename))
            barename = re.sub('.py$', '_bare.py', outname)
            mkdir_p(os.path.dirname(outname))

            module = pool.apply(inspect_module, (module_filename,))
            test_line_count = write_bare_doctest(module, barename)
            if test_line_count:
                test_file_count += 1
                perf_log.extend(pool.apply_async(
                    update_doctests, (barename, outname)).get(timeout=60 * 60))
                os.unlink(barename)

        if test_file_count > 0:
            with open('%s/README' % tmpdir, 'w') as f:
                f.write("\n".join(wrap(
                    "This directory contains self-tests generated by `stbt "
                    "auto-selftests`. Do not modify by hand. Any files "
                    "modified or created in this directory may be overwritten "
                    "or deleted by `stbt auto-selftests`.")) + "\n")

        for x in _recursive_glob('*.pyc', tmpdir):
            os.unlink(os.path.join(tmpdir, x))
        prune_empty_directories(tmpdir)

        print_perf_summary(perf_log, time.time() - start_time)

        return tmpdir
    except:
        pool.terminate()
        pool.join()
        shutil.rmtree(tmpdir)
        raise


class Module(namedtuple('Module', "filename items")):
    pass


class Item(namedtuple('Item', 'name expressions screenshots try_screenshots')):
    pass


def inspect_module(module_filename):
    """
    Pulls the relevant information from the module required to generate tests.
    This is a seperate function so we can run it in a subprocess to avoid
    contaminating the main processes.
    """
    try:
        out = []
        module = import_by_filename(module_filename)
        for x in dir(module):
            item = getattr(module, x)
            if getattr(item, '__module__', None) != module.__name__:
                continue
            expressions = list(getattr(item, 'AUTO_SELFTEST_EXPRESSIONS', []))
            if not expressions:
                continue

            out.append(Item(
                name=item.__name__,
                expressions=expressions,
                screenshots=list(
                    getattr(item, 'AUTO_SELFTEST_SCREENSHOTS', [])),
                try_screenshots=list(
                    getattr(item, 'AUTO_SELFTEST_TRY_SCREENSHOTS', ['*.png']))))
        return Module(module_filename, out)
    except (KeyboardInterrupt, SystemExit):
        raise
    except:  # pylint: disable=bare-except
        sys.stderr.write("Received %s Exception while inspecting %s, Skipping\n"
                         % (sys.exc_info()[1], module_filename))
        return Module(module_filename, [])


def write_bare_doctest(module, output_filename):
    total_tests_written = 0

    outfile = cStringIO.StringIO()
    screenshots_rel = os.path.relpath(
        SCREENSHOTS_ROOT, os.path.dirname(output_filename))
    module_rel = os.path.relpath(
        os.path.dirname(module.filename), os.path.dirname(output_filename))
    outfile.write(dedent(r'''        #!/usr/bin/env python
        # coding=utf-8
        """
        This file contains regression tests automatically generated by
        ``stbt auto-selftest``. These tests are intended to capture the
        behaviour of Frame Objects (and other helper functions that operate on
        a video-frame). Commit this file to git, re-run ``stbt auto-selftest``
        whenever you make a change to your Frame Objects, and use ``git diff``
        to see how your changes affect the behaviour of the Frame Object.

        NOTE: THE OUTPUT OF THE DOCTESTS BELOW IS NOT NECESSARILY "CORRECT" --
        it merely documents the behaviour at the time that
        ``stbt auto-selftest`` was run.
        """
        # pylint: disable=line-too-long

        import os
        import sys

        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), {module_rel}))

        from {name} import *  # isort:skip pylint: disable=wildcard-import, import-error

        _FRAME_CACHE = {{}}


        def f(name):
            img = _FRAME_CACHE.get(name)
            if img is None:
                import cv2
                filename = os.path.join(os.path.dirname(__file__),
                                        {screenshots_rel}, name)
                img = cv2.imread(filename)
                assert img is not None, "Failed to load %s" % filename
                _FRAME_CACHE[name] = img
            return img
        '''.format(name=os.path.basename(module.filename[:-3]),
                   screenshots_rel=repr(screenshots_rel),
                   module_rel=repr(module_rel))))

    for x in module.items:
        total_tests_written += write_test_for_class(x, outfile)
    if total_tests_written > 0:
        with open(output_filename, 'w') as f:
            f.write(outfile.getvalue())
    return total_tests_written


def write_test_for_class(item, out):
    all_screenshots = _recursive_glob('*.png', SCREENSHOTS_ROOT)

    always_screenshots = []
    try_screenshots = []

    for filename in all_screenshots:
        if any(fnmatch.fnmatch(filename, x) for x in item.screenshots):
            always_screenshots.append(filename)
        elif any(fnmatch.fnmatch(filename, x) for x in item.try_screenshots):
            try_screenshots.append(filename)

    if len(always_screenshots) + len(try_screenshots) == 0:
        return 0

    always_screenshots.sort()
    try_screenshots.sort()
    out.write(dedent('''\


        def auto_selftest_{name}():
            r"""
        ''').format(name=item.name))

    for expr in item.expressions:
        for s in always_screenshots:
            out.write("    >>> %s\n" % expr.format(frame='f("%s")' % s))
        for s in try_screenshots:
            out.write("    >>> %s # remove-if-false\n" % expr.format(
                frame='f("%s")' % s))

    out.write('    """\n    pass\n')
    return len(always_screenshots) + len(try_screenshots)


def print_perf_summary(perf_log, total_time):
    perf_log.sort(key=lambda x: -x[1])
    eval_time = sum(x[1] for x in perf_log)
    print "Total time: %fs" % total_time
    print "Total time evaluating: %fs" % eval_time
    print "Overhead: %fs (%f%%)" % (
        total_time - eval_time, 100 * (total_time - eval_time) / total_time)
    print "Number of expressions evaluated: %i" % len(perf_log)
    if len(perf_log) == 0:
        return
    print "Median time: %fs" % perf_log[len(perf_log) // 2][1]
    print "Slowest 10 evaluations:"
    for cmd, duration in perf_log[:10]:
        print "%.03fs\t%s" % (duration, cmd)


def update_doctests(infilename, outfile):
    """
    Updates a file with doctests in it but no results to have "correct" results.
    """
    module = import_by_filename(infilename)
    if isinstance(outfile, str):
        outfile = open(outfile, 'w')

    perf_log = []

    with open(infilename, 'r') as infile, cache():
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
                start_time = time.time()
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
                perf_log.append((cmd, time.time() - start_time))

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

    return perf_log


def test_update_doctests():
    # We test that what we generate is what we expect.  make check-nosetests
    # will check that the generated doctest passes as a doctest itself.
    import subprocess
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile() as outfile:
        test_line_count = len(update_doctests(
            _find_file('tests/auto_selftest_bare.py'), outfile.name))
        assert test_line_count == 19
        actual = outfile.read()
        with open(_find_file('tests/auto_selftest_expected.py')) as f:
            expected = f.read()
        if actual != expected:
            subprocess.call(
                ['diff', '-u', _find_file('tests/auto_selftest_expected.py'),
                 outfile.name])
        assert actual == expected


def _recursive_glob(expr, dir_=None):
    if dir_ is None:
        dir_ = os.curdir
    matches = []
    for root, _, filenames in os.walk(dir_):
        for filename in fnmatch.filter(filenames, expr):
            matches.append(os.path.relpath(os.path.join(root, filename), dir_))
    return matches


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


def _find_test_pack_root():
    root = os.getcwd()
    while root != '/':
        if os.path.exists(os.path.join(root, '.stbt.conf')):
            return root
        root = os.path.split(root)[0]


def import_by_filename(filename_):
    module_dir, module_file = os.path.split(filename_)
    module_name, module_ext = os.path.splitext(module_file)
    if module_ext != '.py':
        raise ImportError("Invalid module filename '%s'" % filename_)
    sys.path = [os.path.abspath(module_dir)] + sys.path
    return __import__(module_name)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
