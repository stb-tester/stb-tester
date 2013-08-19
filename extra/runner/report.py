#!/usr/bin/env python

# Copyright 2013 YouView TV Ltd.
# License: LGPL v2.1 or (at your option) any later version (see
# https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).

"""Generates reports from logs of stb-tester test runs created by 'run'."""

import collections
from datetime import datetime
import glob
import itertools
import os
from os.path import abspath, basename, dirname, isdir
import re
import sys

import jinja2
escape = jinja2.Markup.escape


templates = jinja2.Environment(loader=jinja2.FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "templates")))


def main(argv):
    usage = "Usage: report (index.html | <testrun directory>)"
    if len(argv[1:]) == 0:
        die(usage)
    if argv[1] in ("-h", "--help"):
        print(usage)
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
    rundirs = [
        dirname(x) for x in glob.glob(
            os.path.join(parentdir, "????-??-??_??.??.??*/exit-status"))]
    runs = [Run(d) for d in sorted(rundirs, reverse=True)]
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


class Run:
    def __init__(self, rundir):
        self.rundir = rundir

        self.files = sorted([
            basename(x) for x in glob.glob(rundir + "/*")
            if basename(x) not in [
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
            and not basename(x).startswith("index.html")
        ])
        self.images = sorted([
            basename(x) for x in glob.glob(rundir + "/*.png")])

        self.duration = self.read_seconds("duration")
        self.exit_status = int(self.read("exit-status"))
        self.failure_reason = self.read("failure-reason")
        self.git_commit = self.read("git-commit")
        self.notes = self.read("notes")
        self.test_args = self.read("test-args")
        self.test_name = self.read("test-name")

        self.extra_columns = collections.defaultdict(list)
        for line in self.read("extra-columns").splitlines():
            column, value = line.split("\t", 1)
            self.extra_columns[column.strip()].append(value.strip())

        t = re.match(
            r"\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}", basename(rundir))
        assert t, "Invalid rundir '%s'" % rundir
        self.timestamp = datetime.strptime(t.group(), "%Y-%m-%d_%H.%M.%S")

    def css_class(self):
        if self.exit_status == 0:
            return "success"
        elif self.exit_status == 1:
            return "error"  # Red: Possible system-under-test failure
        else:
            return "warning"  # Yellow: Test infrastructure error

    def read(self, f):
        f = os.path.join(self.rundir, f)
        if os.path.exists(f + ".manual"):
            return escape(open(f + ".manual").read().decode('utf-8').strip())
        elif os.path.exists(f):
            return open(f).read().decode('utf-8').strip()
        else:
            return ""

    def read_seconds(self, f):
        s = self.read(f)
        try:
            s = int(s)
        except ValueError:
            s = 0
        return "%02d:%02d:%02d" % (s / 3600, (s % 3600) / 60, s % 60)


def die(message):
    sys.stderr.write("report: %s\n" % message)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
