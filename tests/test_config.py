import enum
import os
from textwrap import dedent

import pytest

from _stbt.config import (_config_init, _sponge, ConfigurationError,
                          get_config, set_config)
from _stbt.utils import to_unicode


def test_sponge_that_new_data_end_up_in_file(tmp_path):
    path = tmp_path / "hello"
    with _sponge(str(path)) as f:
        f.write('hello')
    assert path.read_text() == 'hello'


def test_sponge_that_on_exception_file_isnt_modified(tmp_path):
    path = tmp_path / "foo"
    path.write_text("bar", encoding='utf-8')

    try:
        with _sponge(str(path)) as f:
            f.write('hello')
            raise RuntimeError()
    except RuntimeError:
        pass
    assert path.read_text() == 'bar'

test_config = dedent("""\
    [global]
    # A comment
    test=hello
    another_test = goodbye""")


@pytest.fixture(name="stbt_config_file")
def _stbt_config_file(monkeypatch, tmp_path):
    test_cfg = tmp_path / "test.cfg"
    monkeypatch.setenv("STBT_CONFIG_FILE", str(test_cfg))
    test_cfg.write_text(test_config, encoding="utf-8")
    yield test_cfg


@pytest.mark.usefixtures("stbt_config_file")
def test_that_set_config_modifies_config_value():
    set_config('global', 'test', 'goodbye')
    assert get_config('global', 'test') == 'goodbye'
    _config_init(force=True)
    assert get_config('global', 'test') == 'goodbye'


@pytest.mark.usefixtures("stbt_config_file")
def test_that_set_config_creates_new_sections_if_required():
    set_config('non_existent_section', 'test', 'goodbye')
    assert get_config('non_existent_section', 'test') == 'goodbye'
    _config_init(force=True)
    assert get_config('non_existent_section', 'test') == 'goodbye'


def test_that_set_config_preserves_file_comments_and_formatting(
    stbt_config_file,
):
    # pylint:disable=fixme,unreachable
    # FIXME: Preserve comments and formatting.  This is fairly tricky as
    # comments and whitespace are not currently stored in Python's internal
    # ConfigParser representation and multiline values makes just using regex
    # tricky.
    from unittest import SkipTest
    raise SkipTest("set_config doesn't currently preserve formatting")
    set_config('global', 'test', 'goodbye')
    expected = test_config.replace("hello", "goodbye")
    assert stbt_config_file.read_text() == expected


def test_that_set_config_creates_directories_if_required(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / '.config'))
    monkeypatch.delenv("STBT_CONFIG_FILE", raising=False)

    set_config('global', 'test', 'hello2')
    assert (tmp_path / '.config/stbt/stbt.conf').is_file()
    _config_init(force=True)
    assert get_config('global', 'test') == 'hello2'


def test_that_set_config_writes_to_the_first_stbt_config_file(
    monkeypatch,
    tmp_path,
):
    filled_cfg = tmp_path / 'test.cfg'
    empty_cfg = tmp_path / 'empty.cfg'
    monkeypatch.setenv("STBT_CONFIG_FILE", f"{filled_cfg}:{empty_cfg}")
    filled_cfg.touch()
    empty_cfg.touch()

    set_config('global', 'test', 'goodbye')
    assert filled_cfg.read_text().startswith('[global]')
    assert empty_cfg.read_text() == ''


class MyEnum(enum.Enum):
    NAME_1 = "value-1"
    NAME_2 = "value-2"


class MyIntEnum(enum.IntEnum):
    NAME_5 = 5
    NAME_6 = 6


def test_to_enum(config_factory):
    config_factory("""\
        [global]
        bystrlc = name_1
        bystruc = NAME_1
        byvallc = value-1
        byvaluc = VALUE-1
        badstr = notakey
        byint = 5
        byintname = NAME_5
        badint = 7
        """
    )

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


@pytest.fixture(name="config_factory")
def _config_factory(monkeypatch, tmp_path):
    """Return a factory for temporary configs.

    The callable has the following signature:
    * contents: str - the contents of the config file
    * filename: str = "stbt-test.cfg" - the name of the config file to
      create
    """
    def factory(contents, filename="stbt-test.cfg"):
        filename = tmp_path / filename
        original_env = os.environ.get("STBT_CONFIG_FILE", "")
        monkeypatch.setenv(
            "STBT_CONFIG_FILE",
            to_unicode(":".join([str(filename), original_env])),
        )
        filename.write_text(dedent(contents), encoding="utf-8")
        _config_init(force=True)

    try:
        yield factory
    finally:
        _config_init(force=True)


def test_unicode_in_STBT_CONFIG_FILE(config_factory):
    config_factory(test_config, filename="\xf8.cfg")
    assert get_config("global", "test") == "hello"


def test_unicode_in_config_file_contents(config_factory):
    config_factory("""\
        [global]
        unicodeinkey\xf8 = hi
        unicodeinvalue = \xf8

        [unicodeinsection\xf8]
        key = bye
        """
    )

    assert get_config("global", "unicodeinkey\xf8") == "hi"
    assert get_config("global", "unicodeinvalue") == "\xf8"
    assert get_config("unicodeinsection\xf8", "key") == "bye"
    assert isinstance(get_config("global", "unicodeinvalue"), str)


def test_get_config_with_default_value(config_factory):
    config_factory("""\
        [global]
        test=hello"""
    )

    assert get_config("global", "test", "my default") == "hello"
    assert get_config("global", "nosuchkey", "my default") == "my default"
    assert get_config("nosuchsection", "test", "my default") == "my default"
    assert get_config("nosuchsection", "test", None) is None
    with pytest.raises(ConfigurationError):
        get_config("nosuchsection", "test")
