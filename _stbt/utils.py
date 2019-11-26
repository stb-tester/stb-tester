"""Copyright 2014-2019 Stb-tester.com Ltd.

This file shouldn't depend on anything else in stbt.
"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import errno
import os
import sys
import tempfile
from contextlib import contextmanager
from shutil import rmtree


def mkdir_p(d):
    """Python 3.2 has an optional argument to os.makedirs called exist_ok.  To
    support older versions of python we can't use this and need to catch
    exceptions"""
    try:
        os.makedirs(d)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(d) \
                and os.access(d, os.R_OK | os.W_OK):
            return
        else:
            raise


def rm_f(filename):
    """Like ``rm -f``, it ignores errors if the file doesn't exist."""
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


@contextmanager
def named_temporary_directory(
        suffix='', prefix='tmp', dir=None):  # pylint:disable=redefined-builtin,redefined-outer-name
    dirname = tempfile.mkdtemp(suffix, prefix, dir)
    try:
        yield dirname
    finally:
        rmtree(dirname)


@contextmanager
def scoped_curdir():
    with named_temporary_directory() as tmpdir:
        olddir = os.path.abspath(os.curdir)
        os.chdir(tmpdir)
        try:
            yield olddir
        finally:
            os.chdir(olddir)


@contextmanager
def scoped_process(process):
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def find_import_name(filename):
    """
    To import an arbitrary filename we need to set PYTHONPATH and we need to
    know the name of the module we're importing.  This is complicated by Python
    packages: for a directory structure like this:

        tests/package/a.py
        tests/package/__init__.py

    we want to add `tests` to `PYTHONPATH` (`sys.path`) and `import package.a`.
    This function traverses the directories to work out what `PYTHONPATH` and
    the module name should be returning them as a tuple.
    """
    import_dir, module_file = os.path.split(os.path.abspath(filename))
    import_name, module_ext = os.path.splitext(module_file)
    if module_ext != '.py':
        raise ImportError("Invalid module filename '%s'" % filename)

    while os.path.exists(os.path.join(import_dir, "__init__.py")):
        import_dir, s = os.path.split(import_dir)
        import_name = "%s.%s" % (s, import_name)
    return import_dir, import_name


if sys.version_info.major == 2:  # Python 2
    text_type = unicode  # pylint: disable=undefined-variable

    def strip_newtypes(text):
        """python-future's string newtypes can behave in surprising ways.  We
        want to avoid returning them in our APIs and we need to cope with
        handling them internally, so we have this function."""
        # newbytes overrides __instancecheck__, so we can't use isinstance to
        # check if it's an instance
        typename = type(text).__name__
        if typename == b"newbytes":
            from future.types.newbytes import newbytes
            # newbytes derives from bytes, but overloads __str__, adding a b'
            # prefix, so we avoid this by calling the base class
            return super(newbytes, text).__str__()
        elif typename == b'newstr':
            return unicode(text)  # pylint: disable=undefined-variable
        else:
            return text

    def test_strip_newtypes():
        from future.types.newbytes import newbytes
        from future.types.newstr import newstr

        def check(x, y):
            assert x == y
            assert type(x).__name__ == type(y).__name__

        check(strip_newtypes(newstr("abc")), "abc")
        check(strip_newtypes(newbytes(b"abc")), b"abc")
else:
    text_type = str

    def strip_newtypes(text):
        # newtypes won't be used on Python 3
        return text


native_str = str
native_int = int


def to_bytes(text):
    text = strip_newtypes(text)

    if isinstance(text, text_type):
        return text.encode("utf-8", errors="backslashreplace")
    elif isinstance(text, bytes):
        return text
    else:
        raise TypeError("Unexpected type %s" % type(text))


def to_unicode(text):
    text = strip_newtypes(text)

    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    else:
        return text_type(text)


if sys.version_info.major == 2:  # Python 2
    def to_native_str(text):
        return to_bytes(text)
else:  # Python 3
    def to_native_str(text):
        return to_unicode(text)
