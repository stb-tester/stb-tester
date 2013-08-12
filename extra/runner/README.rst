Test runner & reporting system
==============================

run
---

This::

    run path/to/test.py another/test.py

will run the given stb-tester scripts until one of them fails. You can run the
tests once, or keep going after uninteresting failures, or keep going no matter
what; see ``run -h`` for help.

``run`` creates a separate timestamped directory for each test run, containing
the logs from that run.

report
------

After each test run, ``run`` executes ``report`` to classify the failure
reason, gather other useful information, and generate a static html report in
``index.html``. So the way you should use ``run`` is something like this::

    mkdir my-test-session
    cd my-test-session
    run path/to/test.py &
    firefox index.html

It's up to you to organise "test sessions" as you want them: You can run
further tests from the same directory to add them to the existing report,
or run them from a new directory for a separate report.

See ``report`` for the failure reasons we currently know how to detect.
``run`` executes ``report`` automatically, but you can also re-run
``report`` on old test logs (when you've added new classifications after
those tests were originally run). See ``report -h`` for help.

User hooks
----------

The following hooks are available for custom log collection, failure
classification, and failure recovery. Each hook is a variable in the stbt
configuration file; if the variable is set to an executable program, ``run``
will invoke that program at the appropriate time, with the current working
directory set to the directory containing the test run logs:

**runner.pre_run**
  Invoked immediately before the test is run, with the
  single command-line argument "start". Intended for starting custom logging
  processes.

**runner.post_run**
  Invoked as soon as possible after the test has completed, with the single
  command-line argument "stop" (so that you can set ``pre_run`` and
  ``post_run`` to the same program). Intended for stopping custom logging
  processes and gathering any other data that must be gathered immediately
  after the test has run.

  The program should save all logs to the current working directory. This
  program should not do any expensive analysis that could be done later.

  Communication between the ``pre_run`` and the ``post_run`` programs
  can be achieved by writing files to the current working directory (for
  example pid files), which the ``post_run`` program should clean up.

**runner.recover**
  Invoked after the test has failed. This program should restore the
  system-under-test to a state where it is ready to run the next test (for
  example by power-cycling the system-under-test and ensuring the boot sequence
  completes). This program is invoked after the built-in classification and the
  custom ``classify`` program, so the output from that classification is
  available (see below).

  This program should return a non-zero exit status to indicate that recovery
  was unsuccessful and no further tests should be run.

**runner.classify**
  Invoked after the test has completed (after the ``post_run`` program and
  after the built-in classification / log analysis). Intended for additional
  analysis of the log files. This program is also invoked when ``report`` is
  run by the user, so this program shouldn't rely on any information from the
  live test-run environment.

  The current working directory will contain the following files:

  * ``test-name`` (containing the path to the test script).
  * ``exit-status`` (containing the numeric exit status from ``stbt run``).
  * ``failure-reason`` (containing the failure reason determined by the
    built-in classification -- see ``report`` for details).
  * ``duration`` (containing the test-run duration in seconds).
  * ``stdout.log``, ``stderr.log`` (containing the output from ``stbt run``).
  * ``sensors.log`` (if ``lm-sensors`` is installed; contains hardware sensor
    readings such as CPU temperature).
  * ``backtrace.log`` (if ``stbt run`` dumped core).
  * ``screenshot-clean.png`` (taken as soon as the test failed).
  * ``template.png`` (if the test failed due to a MatchTimeout; contains the
    image that the ``wait_for_match`` or ``detect_match`` function failed to
    find).

  The program can choose to leave the ``failure-reason`` file unchanged, or to
  overwrite the file with a new failure reason. The failure reason is an
  arbitrary string that is shown in the "Exit status" column of the html
  report.

  The program can add additional columns to the html report by writing to the
  file ``extra-columns``. Each line should contain a key (the column header),
  followed by a tab, followed by a value (arbitrary text). Multiple lines with
  the same key will have their values merged into a single column. The program
  should append to the ``extra-columns`` file, not overwrite it.

server
------

The generated report is a set of static html files, which you can view locally
(using a `file:///...` url), or you can serve them with a web server like
apache. But if you want to interactively *edit* the report, you can run our
``server``. By default, ``server`` serves on ``localhost:5000``. To serve on
all public network interfaces, run it like this:

    server 0.0.0.0:5000

Run ``server`` from the directory containing the test results (for example
``my-test-session`` in the "report" section above).

``server`` probably can't handle high loads or many concurrent users. For such
cases you should proxy ``server`` behind Apache or Nginx. ``server`` uses
"Flask", a python web micro-framework; for deployment options see
http://flask.pocoo.org/docs/deploying/
