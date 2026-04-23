# pytest configuration

import os
from pathlib import Path
from typing import Generator

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


@pytest.fixture(name="cwd_is_tmp_path")
def _cwd_is_tmp_path(tmp_path: Path) -> Generator[None, None, None]:
    """Change the CWD to a temporary directory for the duration of a test."""
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield
    finally:
        os.chdir(orig_cwd)
