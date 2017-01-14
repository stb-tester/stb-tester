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
from astroid.node_classes import BinOp
from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker

try:
    from astroid.node_classes import Call, Expr, Keyword
    from astroid.scoped_nodes import ClassDef, FunctionDef
except ImportError:
    from astroid.node_classes import CallFunc as Call, Discard as Expr, Keyword
    from astroid.scoped_nodes import Class as ClassDef, Function as FunctionDef


class StbtChecker(BaseChecker):
    __implements__ = IAstroidChecker
    name = 'stb-tester'
    msgs = {
        # Range 70xx reserved for custom checkers: www.logilab.org/ticket/68057
        # When you add a new checker update the docstring in ../stbt-lint
        'E7001': ('Image "%s" not found on disk',
                  'stbt-missing-image',
                  'The image path given to "stbt.match" '
                  '(and similar functions) does not exist on disk.'),
        'E7002': ('"%s" return value not used (missing "assert"?)',
                  'stbt-unused-return-value',
                  "This function does not raise an exception on failure but "
                  "you aren't using its return value. Perhaps you've forgotten "
                  'to use "assert".'),
        'E7003': ('"wait_until" argument "%s" isn\'t callable',
                  'stbt-wait-until-callable',
                  'The argument given to "wait_until" must be a callable '
                  '(such as a function or a lambda expression).'),
        'E7004': ('"%s" missing "frame" argument',
                  'stbt-frame-object-missing-frame',
                  'FrameObject properties must always provide "self._frame" as '
                  'the "frame" parameter to functions such as "stbt.match".'),
    }

    def visit_const(self, node):
        if (isinstance(node.value, str) and
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
            if isinstance(node.parent, Expr):
                for inferred in node.func.infer():
                    if inferred.root().name in ('stbt', '_stbt.core'):
                        self.add_message(
                            'E7002', node=node, args=node.func.as_string())

        if re.search(r"\bwait_until", node.func.as_string()):
            if node.args:
                arg = node.args[0]
                for inferred in arg.infer():
                    # Note that when `infer()` fails it returns `YES` which
                    # returns True to everything (including `callable()`).
                    if inferred.callable() and not (
                            isinstance(arg, Call) and inferred == YES):
                        break
                else:
                    self.add_message('E7003', node=node, args=arg.as_string())

        if _in_frameobject(node) and _in_property(node):
            for funcdef in node.func.infer():
                if (isinstance(funcdef, FunctionDef) and
                        funcdef != YES and
                        "frame" in funcdef.argnames()):
                    index = funcdef.argnames().index("frame")
                    args = [a for a in node.args if not isinstance(a, Keyword)]
                    if hasattr(node, "keywords"):  # astroid >= 1.4
                        keywords = node.keywords or []
                        kwargs = [k.arg for k in keywords]
                    else:  # astroid < 1.4
                        kwargs = [a.arg for a in node.args
                                  if isinstance(a, Keyword)]
                    if len(args) <= index and "frame" not in kwargs:
                        self.add_message('E7004', node=node,
                                         args=node.as_string())


def _in_frameobject(node):
    while node is not None:
        if isinstance(node, ClassDef):
            if "stbt.FrameObject" in [
                    base.qname() for base in node.ancestors()]:
                return True
        node = node.parent
    return False


def _in_property(node):
    while node is not None:
        if isinstance(node, FunctionDef):
            if "__builtin__.property" in node.decoratornames():
                return True
        node = node.parent
    return False


def _is_calculated_value(node):
    return (
        isinstance(node.parent, BinOp) or
        (isinstance(node.parent, Call) and
         node.parent.func.as_string().split(".")[-1] == "join"))


def _is_pattern_value(node):
    return re.search(r'\*', node.value)


def _is_whitelisted_name(filename):
    return filename == 'screenshot.png'


def _in_whitelisted_functions(node):
    return (
        isinstance(node.parent, Call) and
        any(_is_function_named(node.parent.func, x) for x in (
            "cv2.imwrite",
            "re.match",
            "re.search",
            "stbt.save_frame",
            "_stbt.core.save_frame",  # handles "from stbt import save_frame"
        )))


def _is_function_named(func, name):
    if func.as_string() == name:
        return True
    for funcdef in func.infer():
        if (isinstance(funcdef, FunctionDef) and funcdef != YES and
                ".".join((funcdef.parent.name, funcdef.name)) == name):
            return True
    return False


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
