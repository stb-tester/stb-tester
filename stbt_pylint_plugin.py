"""pylint plugin to do static analysis on stbt scripts

* Identifies broken image links in parameters to `stbt.wait_for_match` etc.

Intended to be used by "stbt lint".

Documentation on Abstract Syntax Tree traversal with python/pylint:

* http://www.logilab.org/card/pylint_manual#writing-your-own-checker
* http://hg.logilab.org/review/pylint/file/default/examples/custom.py
* http://docs.python.org/2/library/ast.html

"""

import os
import re

# Install `pylint` to get `logilab.astng` modules.
from logilab.astng.node_classes import BinOp, CallFunc, Getattr
from pylint.checkers import BaseChecker

try:  # >= pylint 1.0
    from pylint.interfaces import IAstroidChecker  # pylint: disable=E0611
except ImportError:  # < pylint 1.0
    from pylint.interfaces import IASTNGChecker as IAstroidChecker  # pylint: disable=E0611,C0301


class StbtChecker(BaseChecker):
    __implements__ = IAstroidChecker  # pylint: disable=F0220
    name = 'stb-tester'
    msgs = {
        # Range 70xx reserved for custom checkers: www.logilab.org/ticket/68057
        'E7001': ('Image "%s" not found on disk',
                  'Used when the image path given to `stbt.wait_for_match` '
                  '(and similar functions) does not exist on disk.'),
    }

    def visit_const(self, node):
        if (type(node.value) is str and
                re.search(r'.png$', node.value) and
                not _is_calculated_value(node) and
                not _is_pattern_value(node) and
                not _is_whitelisted_name(node.value) and
                not _in_whitelisted_functions(node) and
                not _file_exists(node.value, node)):
            self.add_message('E7001', node=node, args=node.value)


def _is_calculated_value(node):
    return (
        type(node.parent) is BinOp or
        (type(node.parent) is CallFunc and
         type(node.parent.func) is Getattr and
         node.parent.func.attrname == 'join'))


def _is_pattern_value(node):
    return re.search(r'\*', node.value)


def _is_whitelisted_name(filename):
    return filename == 'screenshot.png'


def _in_whitelisted_functions(node):
    return (
        type(node.parent) is CallFunc and
        node.parent.func.as_string() in (
            "re.match",
            "re.search",
            "stbt.save_frame",
        ))


def _file_exists(filename, node):
    """True if `filename` is found on stbt's image search path

    (See commit 4e5cd23c.)
    """
    if os.path.isfile(os.path.join(
            os.path.dirname(node.root().file),
            filename)):
        return True
    return False


def register(linter):
    linter.register_checker(StbtChecker(linter))
