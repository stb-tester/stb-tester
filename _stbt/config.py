import ConfigParser
import os
from contextlib import contextmanager

from . import utils

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
        return type_(config.get(section, key))
    except ConfigParser.Error as e:
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
    `$HOME/stbt/stbt.conf`.
    """
    user_config = xdg_config_dir('stbt/stbt.conf')
    # Write to the config file with the highest precedence
    custom_config = os.environ.get('STBT_CONFIG_FILE', '').split(':')[0] \
        or user_config

    config = _config_init()

    parser = ConfigParser.SafeConfigParser()
    parser.read([custom_config])
    if value is not None:
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, option, value)
    else:
        try:
            parser.remove_option(section, option)
        except ConfigParser.NoSectionError:
            pass

    d = os.path.dirname(custom_config)
    utils.mkdir_p(d)
    with _sponge(custom_config) as f:
        parser.write(f)

    if value is not None:
        if not config.has_section(section):
            config.add_section(section)
        config.set(section, option, value)


def _config_init(force=False):
    global _config
    if force or not _config:
        config = ConfigParser.SafeConfigParser()
        config.readfp(
            open(os.path.join(os.path.dirname(__file__), '..', 'stbt.conf')))
        try:
            # Host-wide config, e.g. /etc/stbt/stbt.conf (see `Makefile`).
            system_config = config.get('global', '__system_config')
        except ConfigParser.NoOptionError:
            # Running `stbt` from source (not installed) location.
            system_config = ''
        config.read(
            [system_config,
             # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
             # directory specification:
             xdg_config_dir('stbt/stbt.conf')] +
            # Config files specific to the test suite / test run,
            # with the one at the beginning taking precedence:
            list(reversed(os.environ.get('STBT_CONFIG_FILE', '').split(':')))
        )
        _config = config
    return _config


def xdg_config_dir(subdir=''):
    config_dir = os.environ.get(
        'XDG_CONFIG_HOME', '%s/.config' % os.environ['HOME'])
    return os.path.join(config_dir, subdir)


@contextmanager
def _sponge(filename):
    """Opens a file to be written, which will be atomically replaced if the
    contextmanager exits cleanly.  Useful like the UNIX moreutils command
    `sponge`
    """
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(prefix=filename + '.', suffix='~',
                            delete=False) as f:
        try:
            yield f
            os.rename(f.name, filename)
        except:
            os.remove(f.name)
            raise
