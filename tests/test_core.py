import time

import stbt


def test_that_wait_until_returns_on_success():
    count = [0]

    def t():
        count[0] += 1
        return True

    assert stbt.wait_until(t)
    assert count == [1]


def test_that_wait_until_times_out():
    start = time.time()
    assert not stbt.wait_until(lambda: False, timeout_secs=0.1)
    end = time.time()
    assert 0.1 < end - start < 0.2
