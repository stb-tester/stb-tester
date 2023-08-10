# pytest configuration

import os

import pytest

import _stbt.logging


_stbt.logging._debug_level = 1


@pytest.fixture(scope="function")
def test_pack_root():
    import stbt_core
    stbt_core.TEST_PACK_ROOT = os.path.abspath(os.path.dirname(__file__))
    try:
        yield
    finally:
        stbt_core.TEST_PACK_ROOT = None
