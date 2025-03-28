from __future__ import annotations

import configparser
import enum
import os
import typing
from contextlib import contextmanager
from typing import Callable, Type, TypeVar


DefaultT = TypeVar('DefaultT')
T = TypeVar('T')

_config = None


class ConfigurationError(Exception):
    """An error with your stbt configuration file."""


class NoDefault():
    pass


@typing.overload
def get_config(
    section: str,
    key: str,
    *,
    type_: Callable[[str], T] = str,
) -> "T":
    ...


@typing.overload
def get_config(
    section: str,
    key: str,
    default: DefaultT,
    type_: Callable[[str], T] = str,
) -> "T | DefaultT":
    ...


def get_config(
    section: str,
    key: str,
    default: DefaultT | Type[NoDefault] = NoDefault,
    type_: Callable[[str], T] = str,
) -> "T | DefaultT":
    """Read the value of ``key`` from ``section`` of the test-pack
    configuration file.

    For example, if your configuration file looks like this::

        [test_pack]
        stbt_version = 30

        [my_company_name]
        backend_ip = 192.168.1.23

    then you can read the value from your test script like this::

        backend_ip = stbt.get_config("my_company_name", "backend_ip")

    This searches in the ``.stbt.conf`` file at the root of your test-pack, and
    in the ``config/test-farm/<hostname>.conf`` file matching the hostname of
    the stb-tester device where the script is running. Values in the
    host-specific config file override values in ``.stbt.conf``. See
    `Configuration files
    <https://stb-tester.com/manual/configuration#configuration-files>`__
    for more details.

    Test scripts can use ``get_config`` to read tags that you specify at
    run-time: see `Automatic configuration keys
    <https://stb-tester.com/manual/configuration#automatic-configuration-keys>`__.
    For example::

        my_tag_value = stbt.get_config("result.tags", "my tag name")

    Raises `ConfigurationError` if the specified ``section`` or ``key`` is not
    found, unless ``default`` is specified (in which case ``default`` is
    returned).
    """

    config = _config_init()

    try:
        if type_ is bool:
            return config.getboolean(section, key)  # type:ignore
        elif issubclass(type_, enum.Enum):  # type:ignore
            return _to_enum(type_, config.get(section, key), section, key)
        else:
            return type_(config.get(section, key))  # type:ignore
    except configparser.Error as e:
        if default is NoDefault:
            raise ConfigurationError(e.message)
        else:
            return default  # type:ignore
    except ValueError as e:
        raise ConfigurationError("'%s.%s' invalid type (must be %s): %s" % (
            section, key, type_.__name__, e))


def set_config(section, option, value):
    """Update config values (in memory and on disk).

    WARNING: This will overwrite your stbt.conf but comments and whitespace
    will not be preserved.  For this reason it is not a part of stbt's public
    API.  This is a limitation of Python's ConfigParser which hopefully we can
    solve in the future.

    Writes to the first item in `$STBT_CONFIG_FILE` if set falling back to
    `$HOME/.config/stbt/stbt.conf`.
    """
    from .utils import mkdir_p

    user_config = '%s/stbt/stbt.conf' % xdg_config_dir()
    # Write to the config file with the highest precedence
    custom_config = os.environ.get('STBT_CONFIG_FILE', '').split(':')[0] \
        or user_config

    config = _config_init()

    parser = configparser.ConfigParser()
    parser.read([custom_config])
    if value is not None:
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, option, value)
    else:
        try:
            parser.remove_option(section, option)
        except configparser.NoSectionError:
            pass

    d = os.path.dirname(custom_config)
    mkdir_p(d)
    with _sponge(custom_config) as f:
        parser.write(f)

    if value is not None:
        if not config.has_section(section):
            config.add_section(section)
        config.set(section, option, value)


def _config_init(force=False):
    global _config
    if force or not _config:
        config_files = [_find_file('stbt.conf')]
        try:
            # Host-wide config, e.g. /etc/stbt/stbt.conf (see `Makefile`).
            from .vars import sysconfdir  # type:ignore
        except ImportError:
            sysconfdir = "/etc"
        config_files.append(os.path.join(sysconfdir, 'stbt/stbt.conf'))

        # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
        # directory specification:
        config_files.append('%s/stbt/stbt.conf' % xdg_config_dir())

        # Config files specific to the test suite / test run,
        # with the one at the beginning taking precedence:
        config_files.extend(
            reversed(os.environ.get('STBT_CONFIG_FILE', '')
                     .split(':')))
        config = configparser.ConfigParser()
        config.read(config_files)
        _config = config
    return _config


def xdg_config_dir():
    return os.environ.get('XDG_CONFIG_HOME', '%s/.config' % os.environ['HOME'])


def _to_enum(type_, value, section, key):
    # Try enum name
    try:
        return type_[value.upper()]
    except KeyError:
        pass

    # Try enum value
    try:
        if issubclass(type_, enum.IntEnum):
            value = int(value)
        return type_(value)
    except ValueError:
        pass

    raise ConfigurationError(
        'Invalid config value %s.%s="%s". Valid values are %s.'
        % (section, key, value, ", ".join(x.name for x in type_)))


@contextmanager
def _sponge(filename, mode="w"):
    """Opens a file to be written, which will be atomically replaced if the
    contextmanager exits cleanly.  Useful like the UNIX moreutils command
    `sponge`
    """
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode=mode, prefix=filename + '.', suffix='~',
                            delete=False) as f:
        try:
            yield f
            os.rename(f.name, filename)
        except:
            os.remove(f.name)
            raise


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)
