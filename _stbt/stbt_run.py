import os
import sys
import traceback
from collections import namedtuple
from contextlib import contextmanager

from stbt_core import _set_dut_singleton
from _stbt.types import UITestFailure
from _stbt.utils import find_import_name


def _save_screenshot(dut, result_dir, exception, save_jpg, save_png):
    import cv2

    if not save_jpg and not save_png:
        return

    screenshot = getattr(exception, "screenshot", None)
    if screenshot is None and dut._display:
        screenshot = dut._display.last_used_frame
    if screenshot is None:
        screenshot = dut.get_frame()

    if save_png:
        cv2.imwrite(os.path.join(result_dir, "screenshot.png"), screenshot)
        sys.stderr.write("Saved screenshot to 'screenshot.png'.\n")

    if save_jpg:
        cv2.imwrite(
            os.path.join(result_dir, 'thumbnail.jpg'),
            cv2.resize(screenshot, (
                640, 640 * screenshot.shape[0] // screenshot.shape[1])),
            [cv2.IMWRITE_JPEG_QUALITY, 50])


@contextmanager
def video(args, dut):
    result_dir = os.path.abspath(os.curdir)
    with _set_dut_singleton(dut), dut:
        try:
            yield
        except Exception as e:
            try:
                _save_screenshot(dut, result_dir, exception=e,
                                 save_jpg=(args.save_thumbnail != 'never'),
                                 save_png=(args.save_screenshot != 'never'))
            except Exception:  # pylint: disable=broad-except
                pass
            raise
        else:
            _save_screenshot(dut, result_dir, exception=None,
                             save_jpg=(args.save_thumbnail == 'always'),
                             save_png=(args.save_screenshot == 'always'))


def _import_by_filename(filename_):
    from importlib import import_module
    import_dir, import_name = find_import_name(filename_)
    sys.path.insert(0, import_dir)
    try:
        mod = import_module(import_name)
    finally:
        # If the test function is not in a module we will need to leave
        # PYTHONPATH modified here so one python file in the test-pack can
        # import other files from the same directory.  We also have to be
        # careful of modules that mess with sys.path:
        if '.' in import_name and sys.path[0] == import_dir:
            sys.path.pop(0)
    return mod


_TestFunction = namedtuple(
    "_TestFunction", "script filename funcname line call")


def load_test_function(script, args):
    sys.argv = [script] + args
    if '::' in script:
        filename, funcname = script.split('::', 1)
        mod = _import_by_filename(filename)
        func = getattr(mod, funcname)
        return _TestFunction(
            script, filename, funcname, func.__code__.co_firstlineno,
            func)
    else:
        filename = os.path.abspath(script)

        test_globals = {
            '__builtins__': __builtins__,
            '__name__': '__main__',
            '__file__': script,
            '__doc__': None,
            '__package__': None,
        }

        def fn():
            sys.path.insert(0, os.path.dirname(filename))
            code = compile(open(filename, "rb").read(),
                           filename,
                           mode="exec",
                           # Don't apply the __future__ imports in force in
                           # this file.
                           dont_inherit=1)
            exec(code, test_globals)  # pylint:disable=exec-used

        return _TestFunction(script, script, "", 1, fn)


@contextmanager
def sane_unicode_and_exception_handling(script):
    try:
        yield
    except Exception as e:  # pylint:disable=broad-except
        error_message = str(e)
        if not error_message and isinstance(e, AssertionError):
            error_message = traceback.extract_tb(sys.exc_info()[2])[-1][3]
        sys.stdout.write("FAIL: %s: %s: %s\n" % (
            script, type(e).__name__, error_message))
        traceback.print_exc(file=sys.stderr)
        if isinstance(e, (UITestFailure, AssertionError)):
            sys.exit(1)  # Failure
        else:
            sys.exit(2)  # Error
