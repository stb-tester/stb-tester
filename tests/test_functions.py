import os


def test_that_this_test_is_run():
    open("touched", "w").close()


def test_that_does_nothing():
    pass


def test_that_asserts_the_impossible():
    assert 1 + 1 == 3


def test_that_chdirs():
    os.chdir("/tmp")


def test_that_dumps_core():
    os.abort()
