"""High-level tests of the dynamic behaviour of stbt batch riports.

Verifies stbt-batch.d/static/edit-testrun.js and stbt-batch.d/instaweb.

Dependencies: `selenium` pip module and Firefox.
"""

import contextlib
import glob
import os
import shutil
import subprocess
import tempfile
import threading
import time

import nose

try:
    # pylint: disable=F0401
    from selenium import webdriver
    from selenium.common import exceptions
except ImportError:
    raise nose.SkipTest("Selenium Python Client Driver is not installed")


REPOSITORY_ROOT = os.path.join(os.path.dirname(__file__), "..")


def generate_stbt_batch_results():
    os.environ["STBT_CONFIG_FILE"] = \
        os.path.join(REPOSITORY_ROOT, "tests", "stbt.conf")
    proc = subprocess.Popen(
        [os.path.join(REPOSITORY_ROOT, "stbt-batch.d", "run"),
         os.path.join(REPOSITORY_ROOT, "tests", "test.py")],
        stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    timer = threading.Timer(60, proc.kill)
    timer.start()
    proc.wait()
    timer.cancel()

    assert proc.poll() == 0, "Error in generating `stbt batch` results"
    assert len(glob.glob("????-??-??_??.??.??")) == 2, \
        "Unexpected number of `stbt batch` results"
    assert len(glob.glob("**/*.manual")) == 0, \
        "Unexpected manual text file is present in `stbt batch` results"


class TestStbtBatchReportPages(object):

    driver = None
    instaweb_process = None
    scratchdir = None

    @classmethod
    def setup_class(cls):
        cls.scratchdir = tempfile.mkdtemp(prefix="stb-tester.")
        os.chdir(cls.scratchdir)
        generate_stbt_batch_results()
        cls.instaweb_process = subprocess.Popen(
            [os.path.join(REPOSITORY_ROOT, "stbt-batch.d", "instaweb")],
            stderr=subprocess.STDOUT, stdout=subprocess.PIPE)  # Hide output
        time.sleep(.5)

    @classmethod
    def teardown_class(cls):
        if cls.instaweb_process:
            cls.instaweb_process.terminate()
        if cls.scratchdir and os.path.isdir(cls.scratchdir):
            shutil.rmtree(cls.scratchdir)

    def setup(self):
        assert self.instaweb_process.poll() is None, \
            "`stbt batch instaweb` terminated unexpectedly"
        self.driver = webdriver.Firefox()
        self.driver.maximize_window()  # Otherwise 'Notes' may be off-screen
        self.driver.get("http://localhost:5000")

    def teardown(self):
        if self.driver:
            self.driver.quit()

    def test_hide_result(self):
        table_row = lambda: self.driver.find_element_by_class_name("success")
        hide_button = lambda: self.driver.find_element_by_class_name(
            "text-error")

        def assert_test_run_removed_from_table():
            try:
                table_row()
            except exceptions.NoSuchElementException:
                pass
            else:
                assert False, "Hidden test run is still in the table"

        # Select passed test run
        table_row().click()

        # Hide test run
        with self.details_frame_focused(), \
                self.assert_index_html_is_generated():
            hide_button().click()
            self.driver.switch_to_alert().accept()
        assert_test_run_removed_from_table()
        with self.details_frame_focused():
            assert hide_button().text == "(Deleted)", \
                "Hide button is still present"
        assert len(glob.glob("????-??-??_??.??.??")) == 1, \
            "Test run directory hasn't been hidden"

        # Verify that changes are persistent
        self.driver.refresh()
        assert_test_run_removed_from_table()

    def test_manual_failure_reason(self):
        self.verify_manual_text("failure-reason")

    def test_manual_notes(self):
        self.verify_manual_text("notes")

    @contextlib.contextmanager
    def details_frame_focused(self):
        self.driver.switch_to_frame("details")
        yield
        self.driver.switch_to_default_content()

    @contextlib.contextmanager
    def assert_index_html_is_generated(self):
        last_modified = os.path.getmtime("index.html")
        yield
        start_time = time.time()
        while os.path.getmtime("index.html") <= last_modified:
            assert time.time() <= start_time + 10, \
                "index.html hasn't been re-generated within 10 seconds"
            time.sleep(.1)

    def verify_manual_text(self, automatic_file_name):
        AUTOMATIC_FILE = os.path.join("latest", automatic_file_name)
        MANUAL_FILE = "%s.manual" % AUTOMATIC_FILE

        AUTOMATIC_TEXT = open(AUTOMATIC_FILE).read().rstrip()[:30] if \
            os.path.isfile(AUTOMATIC_FILE) else ""
        MANUAL_TEXT = "Manual text"

        table_row = lambda: self.driver.find_element_by_class_name("warning")
        paragraph = lambda: self.driver.find_element_by_id(automatic_file_name)

        def change_text(new_text):
            with self.details_frame_focused():
                actions = webdriver.common.action_chains.ActionChains(
                    self.driver)
                actions.double_click(on_element=paragraph())
                actions.send_keys(*[webdriver.common.keys.Keys.BACK_SPACE
                                    for _ in paragraph().text])
                actions.send_keys(new_text)
                actions.perform()
                self.driver.find_element_by_tag_name("form").submit()

        def assert_text_present(text):
            assert text in table_row().text, \
                "Text '%s' hasn't been added to test runs' table" % text
            with self.details_frame_focused():
                assert text in paragraph().text, \
                    "Text '%s' hasn't been added to test run details" % text

        def assert_text_not_present(text):
            assert text not in table_row().text, \
                "Text '%s' is unexpected in test runs' table" % text
            with self.details_frame_focused():
                assert text not in paragraph().text, \
                    "Text '%s' is unexpected in test run details" % text

        # Select failed test run
        table_row().click()

        # Insert manual text
        with self.assert_index_html_is_generated():
            change_text(new_text=MANUAL_TEXT)
        assert_text_present(MANUAL_TEXT)
        assert os.path.isfile(MANUAL_FILE), \
            "Manual text file hasn't been created"
        assert open(MANUAL_FILE).read().rstrip() == MANUAL_TEXT, \
            "Text '%s' hasn't been added to manual text file" % MANUAL_TEXT

        # Verify that changes are persistent
        self.driver.refresh()
        table_row().click()
        assert_text_present(MANUAL_TEXT)

        # Delete manual text
        with self.assert_index_html_is_generated():
            change_text(new_text="")
        assert_text_present(AUTOMATIC_TEXT)
        assert_text_not_present(MANUAL_TEXT)
        assert not os.path.isfile(MANUAL_FILE), \
            "Manual text file hasn't been deleted"

        # Verify that changes are persistent
        self.driver.refresh()
        table_row().click()
        assert_text_present(AUTOMATIC_TEXT)
        assert_text_not_present(MANUAL_TEXT)
