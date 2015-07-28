"""pylint plugin to do static analysis on stbt scripts

* Identifies broken image links in parameters to `stbt.wait_for_match` etc.
* Identifies calls to `wait_until` whose return value isn't used (probably
  missing an `assert`).

Intended to be used by "stbt lint".

Documentation on Abstract Syntax Tree traversal with python/pylint:

* http://docs.pylint.org/extend.html#writing-your-own-checker
* http://hg.logilab.org/review/pylint/file/default/examples/custom.py
* http://docs.python.org/2/library/ast.html

"""

import os
import re

from astroid import YES
from astroid.node_classes import BinOp, CallFunc, Discard, Getattr
from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker


class StbtChecker(BaseChecker):
    __implements__ = IAstroidChecker  # pylint: disable=F0220
    name = 'stb-tester'
    msgs = {
        # Range 70xx reserved for custom checkers: www.logilab.org/ticket/68057
        'E7001': ('Image "%s" not found on disk',
                  'stbt-missing-image',
                  'Used when the image path given to `stbt.wait_for_match` '
                  '(and similar functions) does not exist on disk.'),
        'E7002': ('"%s" return value not used (missing "assert"?)',
                  'stbt-unused-return-value',
                  "This function does not raise an exception on failure but "
                  "you aren't using its return value. Perhaps you've forgotten "
                  'to use "assert".'),
        'E7003': ('"wait_until" argument "%s" isn\'t callable',
                  'stbt-wait-until-callable',
                  '"wait_until" takes a callable (such as a function or a '
                  'lambda expression'),
    }

    def visit_const(self, node):
        if (type(node.value) is str and
                re.search(r'.+\.png$', node.value) and
                not _is_calculated_value(node) and
                not _is_pattern_value(node) and
                not _is_whitelisted_name(node.value) and
                not _in_whitelisted_functions(node) and
                not _file_exists(node.value, node)):
            self.add_message('E7001', node=node, args=node.value)

    def visit_callfunc(self, node):
        if re.search(r"\b(is_screen_black|match|match_text|ocr|wait_until)$",
                     node.func.as_string()):
            if type(node.parent) == Discard:
                self.add_message('E7002', node=node, args=node.func.as_string())

        if re.search(r"\bwait_until", node.func.as_string()):
            if node.args:
                arg = node.args[0]
                for inferred in arg.infer():
                    # Note that when `infer()` fails it returns `YES` which
                    # returns True to everything (including `callable()`).
                    if inferred.callable() and not (
                            type(arg) is CallFunc and inferred == YES):
                        break
                else:
                    self.add_message('E7003', node=node, args=arg.as_string())


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
            "cv2.imwrite",
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
