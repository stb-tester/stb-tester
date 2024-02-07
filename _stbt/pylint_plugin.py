"""pylint plugin to do static analysis on stbt scripts

Used by "stbt lint".

Documentation on Abstract Syntax Tree traversal with python/pylint:

* http://docs.pylint.org/extend.html#writing-your-own-checker
* http://hg.logilab.org/review/pylint/file/default/examples/custom.py
* http://docs.python.org/3.6/library/ast.html

"""

import os
import re
import subprocess

from astroid import (
    Assert, Attribute, BinOp, Call, ClassDef, Const, Expr, FunctionDef,
    JoinedStr, Keyword, MANAGER, Name, Raise, Uninferable)
from astroid.context import InferenceContext
from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker


class StbtChecker(BaseChecker):
    __implements__ = IAstroidChecker
    name = 'stb-tester'
    msgs = {
        # Range 70xx reserved for custom checkers: www.logilab.org/ticket/68057
        # When you add a new checker update the docstring in ../stbt_lint.py
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
        'E7005': ('Image "%s" not committed to git',
                  'stbt-uncommitted-image',
                  'The image path given to "stbt.match" '
                  '(and similar functions) exists on disk, '
                  "but isn't committed to git."),
        'E7006': ('FrameObject properties must use "self._frame", not '
                  '"get_frame()"',
                  'stbt-frame-object-get-frame',
                  'FrameObject properties must use "self._frame", not '
                  '"stbt.get_frame()".'),
        'E7007': ('FrameObject properties must not use "%s"',
                  'stbt-frame-object-property-press',
                  'FrameObject properties must not have side-effects that '
                  'change the state of the device-under-test by calling '
                  '"stbt.press()" or "stbt.press_and_wait()".'),
        'E7008': ('"assert True" has no effect',
                  'stbt-assert-true',
                  '"assert True" has no effect; consider replacing it with a '
                  'comment or a call to "logging.info()".'),
        'E7009': ('FrameObject "refresh()" doesn\'t modify "%s" instance',
                  'stbt-frame-object-refresh',
                  "FrameObjects are immutable, so \"refresh()\" doesn't modify "
                  "the instance you call it on; it returns a new instance. "
                  'For example, instead of "page.refresh()" you need to use '
                  '"page = page.refresh()".'),
    }

    def visit_const(self, node):
        if (isinstance(node.value, str) and
                re.search(r'.+\.png$', node.value) and
                "\n" not in node.value and
                not _is_uri(node.value) and
                not _is_calculated_value(node) and
                not _is_pattern_value(node) and
                not _is_whitelisted_name(node.value) and
                not _in_whitelisted_functions(node)):
            path = _find_file(node.value, node)
            if os.path.isfile(path):
                if _is_file_uncommitted(path):
                    self.add_message('E7005', node=node,
                                     args=os.path.relpath(path))
            else:
                self.add_message('E7001', node=node, args=os.path.relpath(path))

    def visit_call(self, node):
        if re.search(r"\b(is_screen_black|match|match_text|ocr|press_and_wait|"
                     r"wait_until)$",
                     node.func.as_string()):
            if isinstance(node.parent, Expr):
                for inferred in _infer(node.func):
                    if inferred.root().name in (
                            '_stbt.black', '_stbt.match', '_stbt.ocr',
                            '_stbt.transition', '_stbt.wait'):
                        self.add_message(
                            'E7002', node=node, args=node.func.as_string())
                        break

        if re.search(r"\bwait_until$", node.func.as_string()):
            if node.args:
                arg = node.args[0]
                if not _is_callable(arg):
                    self.add_message('E7003', node=node, args=arg.as_string())

        if _in_frameobject(node) and _in_property(node):
            if re.search(r"\bget_frame$", node.func.as_string()):
                self.add_message('E7006', node=node)

            if re.search(
                    r"\b(press|press_and_wait|pressing|press_until_match)$",
                    node.func.as_string()):
                self.add_message('E7007', node=node, args=node.func.as_string())

            for funcdef in _infer(node.func):
                argnames = _get_argnames(funcdef)
                if "frame" in argnames:
                    index = argnames.index("frame")
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
                        break

        if isinstance(node.func, Attribute) and node.func.attrname == "refresh":
            for c in _infer(node.func.expr):
                if _is_frameobject(c._proxied):
                    if isinstance(node.parent, Expr):  # not an assignment
                        self.add_message('E7009', node=node,
                                         args=node.func.expr.as_string())
                        break

    def visit_assert(self, assertion):
        if isinstance(assertion.test, Const) and assertion.test.value is True:
            if assertion.fail:
                self.add_message("E7008", node=assertion)
            else:
                self.add_message("E7008", node=assertion)


def _transform_assert_false_into_raise(assertion):
    if isinstance(assertion.test, Const) and assertion.test.value is False:
        out = Raise(lineno=assertion.lineno,
                    col_offset=assertion.col_offset,
                    parent=assertion.parent)
        exc = Call(parent=out)
        if assertion.fail:
            args = [assertion.fail]
            args[0].parent = exc
        else:
            args = []
        exc.postinit(Name("AssertionError", parent=exc), args)
        out.postinit(exc, None)
        return out


MANAGER.register_transform(Assert, _transform_assert_false_into_raise)


def _is_callable(node):
    failed_to_infer = True
    for inferred in _infer(node):
        failed_to_infer = False
        if inferred.callable():
            return True
    if failed_to_infer:
        if (isinstance(node, Call) and
                _is_function_named(node.func, "functools.partial")):
            return True
    return False


def _in_frameobject(node):
    while node is not None:
        if _is_frameobject(node):
            return True
        node = node.parent
    return False


def _is_frameobject(node):
    return (isinstance(node, ClassDef) and
            "_stbt.frameobject.FrameObject" in [base.qname()
                                                for base in node.ancestors()])


def _in_property(node):
    while node is not None:
        if isinstance(node, FunctionDef):
            if ("__builtin__.property" in node.decoratornames() or
                    "builtins.property" in node.decoratornames()):
                return True
        node = node.parent
    return False


def _get_argnames(node):
    if isinstance(node, FunctionDef):
        return node.argnames()
    if isinstance(node, ClassDef) and node.newstyle:
        for method in node.methods():
            if method.name == "__init__":
                return method.argnames()[1:]
    return []


def _is_uri(filename):
    return re.search(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", filename)


def _is_calculated_value(node):
    return (
        isinstance(node.parent, (BinOp, JoinedStr)) or
        (isinstance(node.parent, Call) and
         node.parent.func.as_string().split(".")[-1] in ("join", "replace")))


def _is_pattern_value(node):
    return re.search(r'\*', node.value)


def _is_whitelisted_name(filename):
    return filename == 'screenshot.png'


def _in_whitelisted_functions(node):
    return (
        isinstance(node.parent, Call) and
        any(_is_function_named(node.parent.func, x) for x in (
            "cv2.imwrite",
            "imwrite",  # handles "from cv2 import imwrite" with OpenCV 3.x
            "re.match",
            "re.search",
            "re.sub",
            "stbt.save_frame",
            "_stbt.imgutils.save_frame",  # "from stbt import save_frame"
        )))


def _is_function_named(func, name):
    if func.as_string() == name:
        return True
    for funcdef in _infer(func):
        if (isinstance(funcdef, FunctionDef) and
                ".".join((funcdef.parent.name, funcdef.name)) == name):
            return True
    return False


def _find_file(filename, node):
    """Resolves `filename` on stbt's image search path

    See `stbt.load_image` for stbt's image lookup algorithm.
    """
    return os.path.join(
        os.path.dirname(node.root().file),
        filename)


def _is_file_uncommitted(filename):
    if not _in_git_repo():
        return False
    try:
        subprocess.check_output(
            ["git", "ls-files", "--error-unmatch", filename],
            stderr=subprocess.STDOUT)
        return False
    except subprocess.CalledProcessError:
        return True


__in_git_repo = None


def _in_git_repo():
    global __in_git_repo
    if __in_git_repo is None:
        try:
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                    stderr=subprocess.STDOUT)
            __in_git_repo = True
        except (OSError, subprocess.CalledProcessError):
            __in_git_repo = False
    return __in_git_repo


def _infer(node):
    try:
        for inferred in node.infer():
            # When `infer()` fails it returns this singleton:
            if inferred is Uninferable:
                continue
            yield inferred
    except Exception:  # pylint:disable=broad-except
        pass


def register(linter):
    InferenceContext.max_inferred = 1000
    linter.register_checker(StbtChecker(linter))
