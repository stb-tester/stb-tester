"""Copyright 2020 Stb-tester.com Ltd."""

from __future__ import annotations

import re
import time
from typing import Optional

from .types import KeyT


class MultiPress():
    """Helper for entering text using `multi-press`_ on a numeric keypad.

    In some apps, the search page allows entering text by pressing the keys on
    the remote control's numeric keypad: press the number "2" once for "A",
    twice for "B", etc.::

        1.,     ABC2    DEF3
        GHI4    JKL5    MNO6
        PQRS7   TUV8    WXYZ9
              [space]0

    To enter text with this mechanism, create an instance of this class and
    call its ``enter_text`` method. For example::

        multipress = stbt.MultiPress()
        multipress.enter_text("teletubbies")

    The constructor takes the following parameters:

    :param dict key_mapping:
        The mapping from number keys to letters. The default mapping is::

            {
                "KEY_0": " 0",
                "KEY_1": "1.,",
                "KEY_2": "abc2",
                "KEY_3": "def3",
                "KEY_4": "ghi4",
                "KEY_5": "jkl5",
                "KEY_6": "mno6",
                "KEY_7": "pqrs7",
                "KEY_8": "tuv8",
                "KEY_9": "wxyz9",
            }

        This matches the arrangement of digits A-Z from ITU E.161 / ISO 9995-8.

        The value you pass in this parameter is merged with the default mapping.
        For example to override the punctuation characters you can specify
        ``key_mapping={"KEY_1": "@1.,-_"}``.

        The dict's key names must match the remote-control key names accepted
        by `stbt.press`. The dict's values are a string or sequence of the
        corresponding letters, in the order that they are entered when pressing
        that key.

    :param float interpress_delay_secs:
        The time to wait between every key-press, in seconds. This defaults to
        0.3, the same default as `stbt.press`.

    :param float interletter_delay_secs:
        The time to wait between letters on the same key, in seconds. For
        example, to enter "AB" you need to press key "2" once, then wait, then
        press it again twice. If you don't wait, the device-under-test would
        see three consecutive keypresses which mean the letter "C".

    .. _multi-press: https://en.wikipedia.org/wiki/Multi-tap
    """

    def __init__(
        self,
        key_mapping: Optional[dict[KeyT, str]] = None,
        interpress_delay_secs: Optional[float] = None,
        interletter_delay_secs: float = 1,
    ):

        mapping = _parse_mapping_from_docstring(MultiPress.__doc__)
        if key_mapping is not None:
            mapping.update(key_mapping)
        self.keys = _letters_to_keys(mapping)

        self.interpress_delay_secs = interpress_delay_secs
        self.interletter_delay_secs = interletter_delay_secs

    def enter_text(self, text: str) -> None:
        """Enter the specified text using multi-press on the numeric keypad.

        :param str text:
            The text to enter. The case doesn't matter (uppercase and lowercase
            are treated the same).
        """

        from stbt_core import debug, press

        text = text.lower()

        # Raise exception early, so we don't enter half the text
        for c in text:
            if c not in self.keys:
                raise ValueError("Don't know how to enter %r" % (c,))

        debug("MultiPress.enter_text: %r" % (text,))

        prev_key = None
        for c in text:
            key, n = self.keys[c]
            if prev_key == key:
                time.sleep(self.interletter_delay_secs)
            for _ in range(n):
                press(key, interpress_delay_secs=self.interpress_delay_secs)
            prev_key = key


def _parse_mapping_from_docstring(s):
    """
    >>> _parse_mapping_from_docstring(MultiPress.__doc__)['KEY_0']
    ' 0'
    >>> _parse_mapping_from_docstring(MultiPress.__doc__)['KEY_9']
    'wxyz9'
    """
    code = []
    in_mapping = False
    for line in s.split("\n"):
        if re.match(r"^            {", line):
            in_mapping = True
        if in_mapping:
            code.append(line)
        if re.match(r"^            }", line):
            break
    return eval("\n".join(code))  # pylint:disable=eval-used


def _letters_to_keys(keys_to_letters):
    """
    >>> sorted(_letters_to_keys({'KEY_1': '1', 'KEY_2': 'abc2'}).items())
    [('1', ('KEY_1', 1)),
     ('2', ('KEY_2', 4)),
     ('a', ('KEY_2', 1)),
     ('b', ('KEY_2', 2)),
     ('c', ('KEY_2', 3))]
    """
    out = {}
    for key, letters in keys_to_letters.items():
        for n, letter in enumerate(letters, start=1):
            out[letter] = (key, n)
    return out
