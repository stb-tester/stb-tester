from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
import enum
import os
from contextlib import contextmanager
from textwrap import dedent

import pytest

from _stbt.config import (_config_init, _sponge, ConfigurationError,
                          get_config, set_config)
from _stbt.utils import named_temporary_directory, scoped_curdir


def test_sponge_that_new_data_end_up_in_file():
    with scoped_curdir():
        with _sponge('hello') as f:
            f.write('hello')
        assert open('hello').read() == 'hello'


def test_sponge_that_on_exception_file_isnt_modified():
    with scoped_curdir():
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
    with scoped_curdir() as d:
        test_cfg = d + '/test.cfg'
        os.environ['STBT_CONFIG_FILE'] = test_cfg
        with open(test_cfg, 'w') as f:
            f.write(test_config)
        yield


def test_that_set_config_modifies_config_value():
    with set_config_test():
        set_config('global', 'test', 'goodbye')
        assert get_config('global', 'test') == 'goodbye'
        _config_init(force=True)
        assert get_config('global', 'test') == 'goodbye'


def test_that_set_config_creates_new_sections_if_required():
    with set_config_test():
        set_config('non_existent_section', 'test', 'goodbye')
        assert get_config('non_existent_section', 'test') == 'goodbye'
        _config_init(force=True)
        assert get_config('non_existent_section', 'test') == 'goodbye'


def test_that_set_config_preserves_file_comments_and_formatting():
    # pylint:disable=fixme,unreachable
    # FIXME: Preserve comments and formatting.  This is fairly tricky as
    # comments and whitespace are not currently stored in Python's internal
    # ConfigParser representation and multiline values makes just using regex
    # tricky.
    from unittest import SkipTest
    raise SkipTest("set_config doesn't currently preserve formatting")
    with set_config_test():
        set_config('global', 'test', 'goodbye')
        assert open('test.cfg', 'r').read() == test_config.replace(
            'hello', 'goodbye')


def test_that_set_config_creates_directories_if_required():
    with scoped_curdir() as d:
        os.environ['XDG_CONFIG_HOME'] = d + '/.config'
        if 'STBT_CONFIG_FILE' in os.environ:
            del os.environ['STBT_CONFIG_FILE']
        set_config('global', 'test', 'hello2')
        assert os.path.isfile(d + '/.config/stbt/stbt.conf')
        _config_init(force=True)
        assert get_config('global', 'test') == 'hello2'


def test_that_set_config_writes_to_the_first_stbt_config_file():
    with scoped_curdir() as d:
        filled_cfg = d + '/test.cfg'
        empty_cfg = d + '/empty.cfg'
        os.environ['STBT_CONFIG_FILE'] = '%s:%s' % (filled_cfg, empty_cfg)
        open(filled_cfg, 'w')
        open(empty_cfg, 'w')
        set_config('global', 'test', 'goodbye')
        assert open(filled_cfg).read().startswith('[global]')
        assert open(empty_cfg).read() == ''


class MyEnum(enum.Enum):
    NAME_1 = "value-1"
    NAME_2 = "value-2"


class MyIntEnum(enum.IntEnum):
    NAME_5 = 5
    NAME_6 = 6


def test_to_enum():
    with temporary_config("""\
            [global]
            bystrlc = name_1
            bystruc = NAME_1
            byvallc = value-1
            byvaluc = VALUE-1
            badstr = notakey
            byint = 5
            byintname = NAME_5
            badint = 7
            """):

        assert get_config("global", "bystrlc", type_=MyEnum) == MyEnum.NAME_1
        assert get_config("global", "bystruc", type_=MyEnum) == MyEnum.NAME_1
        assert get_config("global", "byvallc", type_=MyEnum) == MyEnum.NAME_1

        with pytest.raises(ConfigurationError) as excinfo:
            get_config("global", "byvaluc", type_=MyEnum)
        assert "Valid values are NAME_1, NAME_2" in str(excinfo.value)

        with pytest.raises(ConfigurationError):
            get_config("global", "badstr", type_=MyEnum)

        assert get_config("global", "notset", MyEnum.NAME_1, MyEnum) == \
            MyEnum.NAME_1

        assert get_config("global", "byint", type_=MyIntEnum) == \
            MyIntEnum.NAME_5
        assert get_config("global", "byintname", type_=MyIntEnum) == \
            MyIntEnum.NAME_5

        with pytest.raises(ConfigurationError) as excinfo:
            get_config("global", "badint", type_=MyIntEnum)
        assert "Valid values are NAME_5, NAME_6" in str(excinfo.value)


@contextmanager
def temporary_config(contents):
    with named_temporary_directory(prefix="stbt-test-config") as d:
        original_env = os.environ.get("STBT_CONFIG_FILE", "")
        filename = os.path.join(d, "stbt.conf")
        os.environ["STBT_CONFIG_FILE"] = ":".join([filename, original_env])
        with open(filename, "w") as f:
            f.write(dedent(contents))
        _config_init(force=True)
        try:
            yield
        finally:
            os.environ["STBT_CONFIG_FILE"] = original_env
            _config_init(force=True)
