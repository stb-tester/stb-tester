from fnmatch import fnmatch
from tempfile import NamedTemporaryFile

from _stbt import utils


def test_parse_test_uri__just_filepath():
    with NamedTemporaryFile(prefix='my_test_', suffix='.py') as test_file:
        abspath, funcname, func = utils.parse_test_uri(test_file.name)

    assert fnmatch(abspath, '*/my_test_*.py')
    assert funcname == ''
    assert func is None


def test_parse_test_uri__module_and_function():
    with NamedTemporaryFile(prefix='my_test_', suffix='.py') as test_file:
        test_file.file.writelines([
            'def test_make_snafucate():',
            '    pass',
        ])
        test_file.file.flush()
        abspath, funcname, func = \
            utils.parse_test_uri("%s::test_make_snafucate" % test_file.name)

    assert fnmatch(abspath, '*/my_test_*.py')
    assert funcname == 'test_make_snafucate'
    assert callable(func) and func.func_name == 'test_make_snafucate'
