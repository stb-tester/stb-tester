import pytest

from _stbt.logging import ddebug, debug, scoped_debug_level, warn


@pytest.mark.parametrize("level", [0, 1, 2])
def test_that_debug_can_write_unicode_strings(level):
    with scoped_debug_level(level):
        warn('Prüfungs Debug-Unicode')
        debug('Prüfungs Debug-Unicode')
        ddebug('Prüfungs Debug-Unicode')
