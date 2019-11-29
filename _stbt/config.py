from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import (ascii, chr, filter, hex, input, map, next, oct, open, pow,  # pylint:disable=redefined-builtin,unused-import,wildcard-import,wrong-import-order
                      range, round, super, zip)
from future.utils import native_str

import configparser
import enum
import os
from contextlib import contextmanager

_config = None


class ConfigurationError(Exception):
    """An error with your stbt configuration file."""
    pass


def get_config(section, key, default=None, type_=str):
    """Read the value of `key` from `section` of the stbt config file.

    See 'CONFIGURATION' in the stbt(1) man page for the config file search
    path.

    Raises `ConfigurationError` if the specified `section` or `key` is not
    found, unless `default` is specified (in which case `default` is returned).
    """

    config = _config_init()

    try:
        if type_ is bool:
            return config.getboolean(section, key)
        elif issubclass(type_, enum.Enum):
            return _to_enum(type_, config.get(section, key), section, key)
        else:
            return type_(config.get(section, key))
    except configparser.Error as e:
        if default is None:
            raise ConfigurationError(e.message)
        else:
            return default
    except ValueError:
        raise ConfigurationError("'%s.%s' invalid type (must be %s)" % (
            section, key, type_.__name__))


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
            from .vars import sysconfdir
            config_files.append(os.path.join(sysconfdir, 'stbt/stbt.conf'))
        except ImportError:
            pass

        # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
        # directory specification:
        config_files.append('%s/stbt/stbt.conf' % xdg_config_dir())

        # Config files specific to the test suite / test run,
        # with the one at the beginning taking precedence:
        config_files.extend(
            reversed(os.environ.get('STBT_CONFIG_FILE', '')
                     .split(native_str(':'))))
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
