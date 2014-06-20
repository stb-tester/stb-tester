import os
from contextlib import contextmanager
from textwrap import dedent

from stbt import _config_init, _set_config, _sponge, get_config


@contextmanager
def _directory_sandbox():
    from tempfile import mkdtemp
    from shutil import rmtree
    from os import chdir
    d = mkdtemp()
    try:
        chdir(d)
        yield d
    finally:
        rmtree(d, ignore_errors=True)


def test_sponge_that_new_data_end_up_in_file():
    with _directory_sandbox():
        with _sponge('hello') as f:
            f.write('hello')
        assert open('hello').read() == 'hello'


def test_sponge_that_on_exception_file_isnt_modified():
    with _directory_sandbox():
        open('foo', 'w').write('bar')
        try:
            with _sponge('foo') as f:
                f.write('hello')
                raise RuntimeError()
        except RuntimeError:
            pass
        assert open('foo').read() == 'bar'

test_config = dedent("""\
    [global]
    # A comment
    test=hello
    another_test = goodbye""")


@contextmanager
def set_config_test():
    with _directory_sandbox() as d:
        test_cfg = d + '/test.cfg'
        os.environ['STBT_CONFIG_FILE'] = test_cfg
        with open(test_cfg, 'w') as f:
            f.write(test_config)
        yield


def test_that_set_config_modifies_config_value():
    with set_config_test():
        _set_config('global', 'test', 'goodbye')
        assert get_config('global', 'test', 'goodbye')
        _config_init(force=True)
        assert get_config('global', 'test', 'goodbye')


def test_that_set_config_creates_new_sections_if_required():
    with set_config_test():
        _set_config('non_existent_section', 'test', 'goodbye')
        assert get_config('non_existent_section', 'test', 'goodbye')
        _config_init(force=True)
        assert get_config('non_existent_section', 'test', 'goodbye')


def test_that_set_config_preserves_file_comments_and_formatting():
    # pylint:disable=W0511,W0101
    # FIXME: Preserve comments and formatting.  This is fairly tricky as
    # comments and whitespace are not currently stored in Python's internal
    # ConfigParser representation and multiline values makes just using regex
    # tricky.
    from nose import SkipTest
    raise SkipTest("set_config doesn't currently preserve formatting")
    with set_config_test():
        _set_config('global', 'test', 'goodbye')
        assert open('test.cfg', 'r').read() == test_config.replace(
            'hello', 'goodbye')


def test_that_set_config_creates_directories_if_required():
    with _directory_sandbox() as d:
        os.environ['XDG_CONFIG_HOME'] = d + '/.config'
        if 'STBT_CONFIG_FILE' in os.environ:
            del os.environ['STBT_CONFIG_FILE']
        _set_config('global', 'test', 'hello2')
        assert os.path.isfile(d + '/.config/stbt/stbt.conf')
        _config_init(force=True)
        assert get_config('global', 'test') == 'hello2'
