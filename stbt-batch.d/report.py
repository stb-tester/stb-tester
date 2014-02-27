#!/usr/bin/env python

# Copyright 2013 YouView TV Ltd.
# License: LGPL v2.1 or (at your option) any later version (see
# https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).

"""Generates reports from logs of stb-tester test runs created by 'run'."""

import codecs
import collections
import contextlib
from datetime import datetime
import glob
import itertools
import os
from os.path import abspath, basename, dirname, isdir
import re
import sys
import tempfile
import shutil
import sqlite3

import jinja2
escape = jinja2.Markup.escape


templates = jinja2.Environment(loader=jinja2.FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "templates")))


def main(argv):
    usage = "Usage: report (index.html | <testrun directory>)"
    if len(argv[1:]) == 0:
        die(usage)
    if argv[1] in ("-h", "--help"):
        print usage
        sys.exit(0)
    for target in argv[1:]:
        if isdir(target):
            match = re.match(
                r"(.*/)?\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}(-[^/]+)?$",
                abspath(target))
            if match:
                testrun(match.group())
        elif target.endswith("index.html"):
            index(dirname(target))
        else:
            die("Invalid target '%s'" % target)


def index(parentdir):
    with contextlib.closing(FileCache(parentdir)) as cache:
        rundirs = [
            dirname(x) for x in glob.glob(
                os.path.join(parentdir, "????-??-??_??.??.??*/test-name"))]
        runs = [Run(d, cache) for d in sorted(rundirs, reverse=True)]
    runs = [run for run in runs if run.failed is False]
    if len(runs) == 0:
        die("Directory '%s' doesn't contain any testruns" % parentdir)
    print templates.get_template("index.html").render(
        name=basename(abspath(parentdir)).replace("_", " "),
        runs=runs,
        extra_columns=set(
            itertools.chain(*[x.extra_columns.keys() for x in runs])),
    ).encode('utf-8')


def testrun(rundir):
    print templates.get_template("testrun.html").render(
        run=Run(rundir),
    ).encode('utf-8')


class FileCache(collections.MutableMapping):
    """On file systems that have very high latency file operations or poor
    performance when attempting to get metadata about a file listing using
    stat() this cache can help. It behaves like a dictionary; filepaths are
    keys and the contents of files are values.
    """

    def __init__(self, parentdir):
        """Initialize the database. If it doesn't already exist this will result
        in a new file, 'cache.sqlite', existing in the root of the report
        directory. It is safe to manually delete this file.

        If we fail to open the database because the remote file system corrupted
        it or our last transaction was interrupted and it requires a repair then
        just delete it; it's just a cache and we can start from scratch.
        """
        self.source_filepath = os.path.join(parentdir, 'cache.sqlite')
        if not os.path.isfile(self.source_filepath):
            with open(self.source_filepath, 'wb') as f_out:
                pass
        with contextlib.closing(
            tempfile.NamedTemporaryFile(delete=False,
                                        suffix='.cache.sqlite')) as f_out:
            self.destination_filepath = f_out.name
        shutil.copy2(self.source_filepath, self.destination_filepath)
        try:
            self.connection = sqlite3.connect(self.destination_filepath)
        except:
            os.unlink(self.destination_filepath)
            self.connection = sqlite3.connect(self.destination_filepath)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS
            filecontent(filepath TEXT UNIQUE, contents BLOB)""")

    def close(self):
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.connection:
            self.connection.commit()
            self.connection.close()
            self.connection = None
        if os.path.isfile(self.destination_filepath):
            shutil.copyfile(self.destination_filepath, self.source_filepath)
            os.unlink(self.destination_filepath)

    def __len__(self):
        rows = self.cursor.execute("""SELECT COUNT(*)
                                      FROM filecontent""").fetchall()
        return rows[0]['COUNT(*)']

    def __iter__(self):
        for row in self.cursor.execute("""SELECT * FROM filecontent"""):
            yield row['filepath']

    def __getitem__(self, key):
        for row in self.cursor.execute("""SELECT * FROM filecontent
                                          WHERE filepath = ?""", (key, )):
            return row['contents']
        raise KeyError

    def __setitem__(self, key, value):
        self.cursor.execute("""INSERT OR REPLACE INTO filecontent(filepath,
                                                                  contents)
                               VALUES (?, ?)""", (key, value))
        self.connection.commit()

    def __delitem__(self, key):
        self.cursor.execute("""DELETE FROM filecontent WHERE filepath=?""", key)
        self.connection.commit()

    def __del__(self):
        self.close()


class Run(object):
    def __init__(self, rundir, cache=None):
        """Parse information from a stb-tester runner report subdirctory
        necessary for creating both a test index.html file and for helping
        create the root summary table of test results.

        Pass in a FileCache object as the cache argument if you wish to use
        the 'cache.sqlite' file cache in the root of the stb-tester runner
        report directory to improve performance on slow filesystems. See
        'FileCache' for more information.

        Note that we obtain a directory listing once, and only once, and avoid
        all explicit or implicit calls that execute further directory listings.
        This significantly improves performance on file systems that are not
        assisted by client or server side caches.

        At this point of execution there is no guarantee that rundir exists.
        The stb-tester 'instaweb' server can rename directories to prefix
        a dot in front of them at any time. When processing a large number
        of test run directories on slow file systems it could be the case
        the we reach this point and the 'instaweb' server has renamed the
        directory in the mean time.
        """
        self.rundir = rundir

        if not os.path.isdir(self.rundir):
            self.failed = True
            return
        self.failed = False
        self.cache = cache

        dl = set(self._get_directory_listing())

        try:
            self.exit_status = int(self.read("exit-status", dl))
        except ValueError:
            self.exit_status = "still running"

        self.duration = self.read_seconds("duration", dl)
        self.failure_reason = self.read("failure-reason", dl)
        self.git_commit = self.read("git-commit", dl)
        self.notes = self.read("notes", dl)
        self.test_args = self.read("test-args", dl)
        self.test_name = self.read("test-name", dl)

        if self.exit_status != "still running":
            self.files = sorted([
                x for x in dl if x not in [
                    "duration",
                    "exit-status",
                    "extra-columns",
                    "failure-reason",
                    "git-commit",
                    "test-args",
                    "test-name",
                ]
                and not x.endswith(".png")
                and not x.endswith(".manual")
                and not x.startswith("index.html")
            ])
            self.images = sorted([x for x in dl if x.endswith(".png")])

        self.extra_columns = collections.OrderedDict()
        for line in self.read("extra-columns", dl).splitlines():
            column, value = line.split("\t", 1)
            self.extra_columns.setdefault(column.strip(), [])
            self.extra_columns[column.strip()].append(value.strip())

        t = re.match(
            r"\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}", basename(rundir))
        assert t, "Invalid rundir '%s'" % rundir
        self.timestamp = datetime.strptime(t.group(), "%Y-%m-%d_%H.%M.%S")

    def _get_directory_listing(self):
        return os.listdir(self.rundir)

    def css_class(self):
        if self.exit_status == "still running":
            return "muted"  # White
        elif self.exit_status == 0:
            return "success"
        elif self.exit_status == 1:
            return "error"  # Red: Possible system-under-test failure
        else:
            return "warning"  # Yellow: Test infrastructure error

    def read(self, f, dl):
        f = self._get_path(f, dl)
        if f is None:
            return ""
        if self.cache is not None and f in self.cache:
            return self.cache[f]
        with codecs.open(f, encoding='utf-8') as f_in:
            contents = f_in.read().strip()
        if f.endswith('.manual'):
            contents = escape(contents)
        if self.cache is not None:
            self.cache[f] = contents
        return contents

    def read_seconds(self, f, dl):
        s = self.read(f, dl)
        try:
            s = int(s)
        except ValueError:
            s = 0
        return "%02d:%02d:%02d" % (s / 3600, (s % 3600) / 60, s % 60)

    def _get_path(self, f, dl):
        if f + ".manual" in dl:
            return os.path.join(self.rundir, f + ".manual")
        elif f in dl:
            return os.path.join(self.rundir, f)
        else:
            return None


def die(message):
    sys.stderr.write("report.py: %s\n" % message)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
