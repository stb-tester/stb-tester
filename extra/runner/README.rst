Test runner & reporting system
==============================

run
---

This::

    run path/to/test.py another/test.py

will run the given tests until one of them fails. You can run the tests once,
or keep going after uninteresting failures, or keep going no matter what; see
``run -h`` for help.

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
