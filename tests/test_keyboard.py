import logging
import os
import re
import time
from unittest import mock

import numpy
import pytest
from networkx import NetworkXNoPath

import stbt_core as stbt
from _stbt.keyboard import _keys_to_press, _strip_shift_transitions
from _stbt.transition import Transition, TransitionStatus

# pylint:disable=redefined-outer-name


class DUT():
    """Fake keyboard implementation ("Device Under Test").

    Behaves like the YouTube Search keyboard on Apple TV.
    """
    def __init__(self):
        self.x = 0
        self.y = 1
        self.modes = ["lowercase", "uppercase", "symbols"]
        self.mode = self.modes[0]
        self.symbols_is_shift = False
        self.keys = {
            "lowercase": [
                ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
                "abcdef",
                "ghijkl",
                "mnopqr",
                "stuvwx",
                "yz1234",
                "567890",
                [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
            ],
            "uppercase": [
                ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
                "ABCDEF",
                "GHIJKL",
                "MNOPQR",
                "STUVWX",
                "YZ1234",
                "567890",
                [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
            ],
            "symbols": [
                ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
                "!@#$%&",
                "~*\\/?^",
                "_`;:|=",
                "éñ[]{}",
                "çü.,+-",
                "<>()'\"",
                [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
            ]
        }
        self.pressed = []
        self.entered = ""

    @property
    def selection(self):
        k = self.keys[self.mode][self.y][self.x]
        if self.symbols_is_shift and k == "symbols":
            return "shift"
        else:
            return k

    def handle_press(self, keypress):
        self.pressed.append(keypress)
        mode = self.mode
        selected = self.selection
        logging.debug("DUT.handle_press: Pressed %s", keypress)
        if keypress == "KEY_OK":
            if self.symbols_is_shift and selected == "shift":
                if self.mode == "lowercase":
                    self.mode = "uppercase"
                else:
                    self.mode = "lowercase"
            elif (not self.symbols_is_shift) and selected in self.modes:
                self.mode = selected
            elif len(selected) == 1:  # It's a letter
                self.entered += selected
                if self.symbols_is_shift and self.mode == "uppercase":
                    self.mode = "lowercase"
            else:
                assert False, "Unexpected %s on %r" % (keypress, selected)
        elif keypress == "KEY_UP":
            if self.y == 0:
                assert False, "Unexpected %s on %r" % (keypress, selected)
            else:
                self.y -= 1
        elif keypress == "KEY_DOWN":
            if self.y == 7:
                assert False, "Unexpected %s on %r" % (keypress, selected)
            else:
                self.y += 1
        elif keypress == "KEY_LEFT":
            if self.x == 0 or (self.x == 1 and self.y in [0, 7]):
                assert False, "Unexpected %s on %r" % (keypress, selected)
            elif self.y in [0, 7]:
                # x:   012345
                # x%2: 010101
                if self.x % 2 == 0:
                    self.x -= 2
                else:
                    self.x -= 1
            else:
                self.x -= 1
        elif keypress == "KEY_RIGHT":
            if self.x == 5 or (self.x == 4 and self.y in [0, 7]):
                assert False, "Unexpected %s on %r" % (keypress, selected)
            elif self.y in [0, 7]:
                # x:   012345
                # x%2: 010101
                if self.x % 2 == 0:
                    self.x += 2
                else:
                    self.x += 1
            else:
                self.x += 1
        else:
            assert False, "Unexpected %s on %r" % (keypress, selected)
        logging.debug("DUT.handle_press: Moved from %r (%s) to %r (%s)",
                      selected, mode, self.selection, self.mode)

    def handle_press_and_wait(self, key, **_kwargs):
        self.handle_press(key)
        return Transition(key, None, TransitionStatus.COMPLETE, 0, 0, 0)

    def handle_wait_for_transition_to_end(self, *_args, **_kwargs):
        return Transition(None, None, TransitionStatus.COMPLETE, 0, 0, 0)


class DoubleKeypressDUT(DUT):
    def handle_press(self, keypress):
        super().handle_press(keypress)
        if keypress == "KEY_RIGHT" and self.selection == "b":
            logging.debug("DoubleKeypressDUT.handle_press: Double KEY_RIGHT "
                          "press from a to c skipping over b")
            self.x += 1


class MissedKeypressDUT(DUT):
    def __init__(self):
        super().__init__()
        self._last_press_ignored = False

    def handle_press(self, keypress):
        if keypress == "KEY_OK":
            super().handle_press(keypress)
            return

        # Ignore every other up/down/left/right keypress
        if self._last_press_ignored:
            super().handle_press(keypress)
            self._last_press_ignored = False
        else:
            logging.debug("MissedKeypressDUT.handle_press: Ignoring %s",
                          keypress)
            self._last_press_ignored = True

    def handle_press_and_wait(self, key, **_kwargs):
        self.handle_press(key)
        if self._last_press_ignored:
            status = TransitionStatus.START_TIMEOUT
        else:
            status = TransitionStatus.COMPLETE
        return Transition(key, None, status, 0, 0, 0)


class SlowDUT(DUT):
    def __init__(self):
        super().__init__()
        self._delayed_keypress = None

    def handle_press_and_wait(self, key, **_kwargs):
        logging.debug("SlowDUT.handle_press: delaying %s", key)
        self._delayed_keypress = key
        return Transition(key, None, TransitionStatus.COMPLETE, 0, 0, 0)

    def handle_wait_for_transition_to_end(self, *_args, **_kwargs):
        key = self._delayed_keypress
        self._delayed_keypress = None
        assert key is not None
        super().handle_press(key)
        return Transition(key, None, TransitionStatus.COMPLETE, 0, 0, 0)


@pytest.fixture(scope="function")
def dut():
    dut = DUT()
    with mock.patch("stbt_core.press", dut.handle_press), \
            mock.patch("stbt_core.press_and_wait", dut.handle_press_and_wait), \
            mock.patch("stbt_core.wait_for_transition_to_end",
                       dut.handle_wait_for_transition_to_end):
        yield dut


@pytest.fixture(scope="function")
def double_keypress_dut():
    dut = DoubleKeypressDUT()
    with mock.patch("stbt_core.press", dut.handle_press), \
            mock.patch("stbt_core.press_and_wait", dut.handle_press_and_wait), \
            mock.patch("stbt_core.wait_for_transition_to_end",
                       dut.handle_wait_for_transition_to_end):
        yield dut


@pytest.fixture(scope="function")
def missed_keypress_dut():
    dut = MissedKeypressDUT()
    with mock.patch("stbt_core.press", dut.handle_press), \
            mock.patch("stbt_core.press_and_wait", dut.handle_press_and_wait), \
            mock.patch("stbt_core.wait_for_transition_to_end",
                       dut.handle_wait_for_transition_to_end):
        yield dut


@pytest.fixture(scope="function")
def slow_dut():
    dut = SlowDUT()
    with mock.patch("stbt_core.press", dut.handle_press), \
            mock.patch("stbt_core.press_and_wait", dut.handle_press_and_wait), \
            mock.patch("stbt_core.wait_for_transition_to_end",
                       dut.handle_wait_for_transition_to_end):
        yield dut


class _NotSpecified():  # sentinel value
    pass


def SearchPage(dut, kb, is_visible=True, selection=_NotSpecified,
               property_name="selection"):

    class _SearchPage(stbt.FrameObject):
        """Immutable Page Object representing the test's view of the DUT."""

        def __init__(self, dut, kb, is_visible=True, selection=_NotSpecified):
            super().__init__(
                frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
            self.dut = dut
            self.kb = kb
            self._is_visible = is_visible
            self._selection = selection

        @property
        def is_visible(self):
            return self._is_visible

        @property
        def mode(self):
            if self.kb.modes:
                return self.dut.mode
            else:
                return None

        if property_name == "selection":
            @property
            def selection(self):
                return self._focus_property
        elif property_name == "focus":
            @property
            def focus(self):
                return self._focus_property
        else:
            assert False, f"Unexpected name {property_name!r}"

        @property
        def _focus_property(self):
            # In practice this would use image processing to detect the current
            # selection & mode, then look up the key by region & mode.
            # See test_find_key_by_region for an example.
            if self._selection != _NotSpecified:
                return self._selection
            query = {}
            if self.dut.selection == " ":
                # For test_that_enter_text_finds_keys_by_text
                query = {"text": " "}
            else:
                query = {"name": self.dut.selection}
            if self.kb.modes:
                query["mode"] = self.dut.mode
            key = self.kb.find_key(**query)
            logging.debug("SearchPage.selection: %r", key)
            return key

        def refresh(self, frame=None, **kwargs):
            page = SearchPage(self.dut, self.kb, property_name=property_name)
            logging.debug("SearchPage.refresh: Now on %r", page._focus_property)
            return page

        def enter_text(self, text, retries=2):
            return self.kb.enter_text(text, page=self, retries=retries)

        def navigate_to(self, target, verify_every_keypress=False, retries=2):
            return self.kb.navigate_to(
                target, page=self,
                verify_every_keypress=verify_every_keypress,
                retries=retries)

    return _SearchPage(dut, kb, is_visible, selection)


kb1 = stbt.Keyboard()  # Full model with modes, defined using Grids
MODES_GRID = stbt.Grid(
    region=stbt.Region(x=125, y=95, right=430, bottom=140),
    data=[["lowercase", "uppercase", "symbols"]])
MIDDLE_REGION = stbt.Region(x=125, y=140, right=430, bottom=445)
MIDDLE_GRIDS = {
    "lowercase": stbt.Grid(region=MIDDLE_REGION,
                           data=[
                               "abcdef",
                               "ghijkl",
                               "mnopqr",
                               "stuvwx",
                               "yz1234",
                               "567890"]),
    "uppercase": stbt.Grid(region=MIDDLE_REGION,
                           data=[
                               "ABCDEF",
                               "GHIJKL",
                               "MNOPQR",
                               "STUVWX",
                               "YZ1234",
                               "567890"]),
    "symbols": stbt.Grid(region=MIDDLE_REGION,
                         data=[
                             "!@#$%&",
                             "~*\\/?^",
                             "_`;:|=",
                             "éñ[]{}",
                             "çü.,+-",
                             "<>()'\""])
}
BOTTOM_GRID = stbt.Grid(
    region=stbt.Region(x=125, y=445, right=430, bottom=500),
    data=[[" ", "BACKSPACE", "CLEAR"]])
for mode in ["lowercase", "uppercase", "symbols"]:
    kb1.add_grid(MODES_GRID, mode)
    kb1.add_grid(MIDDLE_GRIDS[mode], mode)
    kb1.add_grid(BOTTOM_GRID, mode)

    # abc ABC #+-
    # ↕ ↕ ↕ ↕ ↕ ↕
    # a b c d e f
    #
    # Note that `add_transition` adds the symmetrical transition
    # (KEY_UP) automatically.
    g = MIDDLE_GRIDS[mode]
    kb1.add_transition("lowercase", g[0, 0].data, "KEY_DOWN", mode)
    kb1.add_transition("lowercase", g[1, 0].data, "KEY_DOWN", mode)
    kb1.add_transition("uppercase", g[2, 0].data, "KEY_DOWN", mode)
    kb1.add_transition("uppercase", g[3, 0].data, "KEY_DOWN", mode)
    kb1.add_transition("symbols", g[4, 0].data, "KEY_DOWN", mode)
    kb1.add_transition("symbols", g[5, 0].data, "KEY_DOWN", mode)

    # 5 6 7 8 9 0
    # ↕ ↕ ↕ ↕ ↕ ↕
    # SPC DEL CLR
    kb1.add_transition(g[0, 5].data, " ", "KEY_DOWN", mode)
    kb1.add_transition(g[1, 5].data, " ", "KEY_DOWN", mode)
    kb1.add_transition(g[2, 5].data, "BACKSPACE", "KEY_DOWN", mode)
    kb1.add_transition(g[3, 5].data, "BACKSPACE", "KEY_DOWN", mode)
    kb1.add_transition(g[4, 5].data, "CLEAR", "KEY_DOWN", mode)
    kb1.add_transition(g[5, 5].data, "CLEAR", "KEY_DOWN", mode)

# Mode changes: For example when "ABC" is selected and we are in
# lowercase mode, pressing OK takes us to "ABC" still selected
# but the keyboard is now in uppercase mode.
for source_mode in ["lowercase", "uppercase", "symbols"]:
    for target_mode in ["lowercase", "uppercase", "symbols"]:
        kb1.add_transition({"name": target_mode, "mode": source_mode},
                           {"name": target_mode, "mode": target_mode},
                           "KEY_OK")

kb2 = stbt.Keyboard()  # uppercase & lowercase modes, defined from edgelist
edgelists = {
    "lowercase": """
        lowercase uppercase KEY_RIGHT
        uppercase symbols KEY_RIGHT
        a lowercase KEY_UP
        b lowercase KEY_UP
        c uppercase KEY_UP
        d uppercase KEY_UP
        e symbols KEY_UP
        f symbols KEY_UP
        a b KEY_RIGHT
        b c KEY_RIGHT
        c d KEY_RIGHT
        d e KEY_RIGHT
        e f KEY_RIGHT
        g h KEY_RIGHT
        h i KEY_RIGHT
        i j KEY_RIGHT
        j k KEY_RIGHT
        k l KEY_RIGHT
        m n KEY_RIGHT
        n o KEY_RIGHT
        o p KEY_RIGHT
        p q KEY_RIGHT
        q r KEY_RIGHT
        s t KEY_RIGHT
        t u KEY_RIGHT
        u v KEY_RIGHT
        v w KEY_RIGHT
        w x KEY_RIGHT
        y z KEY_RIGHT
        z 1 KEY_RIGHT
        1 2 KEY_RIGHT
        2 3 KEY_RIGHT
        3 4 KEY_RIGHT
        5 6 KEY_RIGHT
        6 7 KEY_RIGHT
        7 8 KEY_RIGHT
        8 9 KEY_RIGHT
        9 0 KEY_RIGHT
        a g KEY_DOWN
        b h KEY_DOWN
        c i KEY_DOWN
        d j KEY_DOWN
        e k KEY_DOWN
        f l KEY_DOWN
        g m KEY_DOWN
        h n KEY_DOWN
        i o KEY_DOWN
        j p KEY_DOWN
        k q KEY_DOWN
        l r KEY_DOWN
        m s KEY_DOWN
        n t KEY_DOWN
        o u KEY_DOWN
        p v KEY_DOWN
        q w KEY_DOWN
        r x KEY_DOWN
        s y KEY_DOWN
        t z KEY_DOWN
        u 1 KEY_DOWN
        v 2 KEY_DOWN
        w 3 KEY_DOWN
        x 4 KEY_DOWN
        y 5 KEY_DOWN
        z 6 KEY_DOWN
        1 7 KEY_DOWN
        2 8 KEY_DOWN
        3 9 KEY_DOWN
        4 0 KEY_DOWN
        5 SPACE KEY_DOWN
        6 SPACE KEY_DOWN
        7 BACKSPACE KEY_DOWN
        8 BACKSPACE KEY_DOWN
        9 CLEAR KEY_DOWN
        0 CLEAR KEY_DOWN
        SPACE BACKSPACE KEY_RIGHT
        BACKSPACE CLEAR KEY_RIGHT
    """,
}
edgelists["uppercase"] = re.sub(r"\b[a-z]\b", lambda m: m.group(0).upper(),
                                edgelists["lowercase"])
kb2.add_edgelist(edgelists["lowercase"], mode="lowercase")
kb2.add_edgelist(edgelists["uppercase"], mode="uppercase")
# Mode changes: For example when "ABC" is selected and we are in
# lowercase mode, pressing OK takes us to "ABC" still selected
# but the keyboard is now in uppercase mode.
kb2.add_transition({"mode": "lowercase", "name": "uppercase"},
                   {"mode": "uppercase", "name": "uppercase"},
                   "KEY_OK")
kb2.add_transition({"mode": "uppercase", "name": "lowercase"},
                   {"mode": "lowercase", "name": "lowercase"},
                   "KEY_OK")

kb3 = stbt.Keyboard()  # Simple keyboard, lowercase only
kb3.add_edgelist(edgelists["lowercase"])

# Lowercase + shift (no caps lock).
# This keyboard looks like kb1 but it has a "shift" key instead of the "symbols"
# key; and the other mode keys have no effect.
kb4 = stbt.Keyboard()
kb4.add_edgelist(edgelists["lowercase"].replace("symbols", "shift"),
                 mode="lowercase")
kb4.add_edgelist(edgelists["uppercase"].replace("symbols", "shift"),
                 mode="uppercase")
kb4.add_transition({"mode": "lowercase", "name": "shift"},
                   {"mode": "uppercase", "name": "shift"},
                   "KEY_OK")
kb4.add_transition({"mode": "uppercase", "name": "shift"},
                   {"mode": "lowercase", "name": "shift"},
                   "KEY_OK")
# Pressing OK on a letter when shifted goes to lowercase mode (as well as
# entering that letter).
for k in "abcdefghijklmnopqrstuvwxzy1234567890":
    kb4.add_transition({"mode": "uppercase", "name": k.upper()},
                       {"mode": "lowercase", "name": k},
                       "KEY_OK")

# Same as kb1, but defined in a more succinct way using merge=True
kb5 = stbt.Keyboard()
kb5.add_grid(stbt.Grid(
    region=stbt.Region(x=125, y=95, right=430, bottom=500),
    data=[
        ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
        "abcdef",
        "ghijkl",
        "mnopqr",
        "stuvwx",
        "yz1234",
        "567890",
        [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
    ]), mode="lowercase", merge=True)
kb5.add_grid(stbt.Grid(
    region=stbt.Region(x=125, y=95, right=430, bottom=500),
    data=[
        ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
        "ABCDEF",
        "GHIJKL",
        "MNOPQR",
        "STUVWX",
        "YZ1234",
        "567890",
        [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
    ]), mode="uppercase", merge=True)
kb5.add_grid(stbt.Grid(
    region=stbt.Region(x=125, y=95, right=430, bottom=500),
    data=[
        ["lowercase"] * 2 + ["uppercase"] * 2 + ["symbols"] * 2,
        "!@#$%&",
        "~*\\/?^",
        "_`;:|=",
        "éñ[]{}",
        "çü.,+-",
        "<>()'\"",
        [" "] * 2 + ["BACKSPACE"] * 2 + ["CLEAR"] * 2
    ]), mode="symbols", merge=True)

# Mode changes: For example when "ABC" is selected and we are in
# lowercase mode, pressing OK takes us to "ABC" still selected
# but the keyboard is now in uppercase mode.
for source_mode in ["lowercase", "uppercase", "symbols"]:
    for target_mode in ["lowercase", "uppercase", "symbols"]:
        kb5.add_transition({"name": target_mode, "mode": source_mode},
                           {"name": target_mode, "mode": target_mode},
                           "KEY_OK")


@pytest.mark.parametrize("kb", [kb1, kb2, kb5], ids=["kb1", "kb2", "kb5"])
@pytest.mark.parametrize("property_name", ["selection", "focus"])
def test_enter_text_mixed_case(dut, kb, property_name):
    logging.debug("Keys: %r", kb.G.nodes())
    page = SearchPage(dut, kb, property_name=property_name)
    assert getattr(page, property_name).name == "a"
    assert getattr(page, property_name).text == "a"
    assert getattr(page, property_name).mode == "lowercase"
    page = page.enter_text("Hi there")
    assert getattr(page, property_name).name == "e"
    assert dut.entered == "Hi there"


@pytest.mark.parametrize("kb",
                         [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_enter_text_single_case(dut, kb):
    page = SearchPage(dut, kb)
    assert page.selection.name == "a"
    page = page.enter_text("hi there")
    assert page.selection.name == "e"
    assert dut.entered == "hi there"


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_that_enter_text_uses_minimal_keypresses(dut, kb):
    page = SearchPage(dut, kb)
    assert page.selection.name == "a"
    page.enter_text("gh")
    assert dut.pressed == ["KEY_DOWN", "KEY_OK",
                           "KEY_RIGHT", "KEY_OK"]


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_enter_text_twice(dut, kb):
    """This is really a test of your Page Object's implementation of enter_text.

    You must return the updated page instance.
    """
    page = SearchPage(dut, kb)
    assert page.selection.name == "a"
    page = page.enter_text("g")
    page = page.enter_text("h")
    assert dut.pressed == ["KEY_DOWN", "KEY_OK",
                           "KEY_RIGHT", "KEY_OK"]


def test_that_enter_text_finds_keys_by_text(dut):
    kb = stbt.Keyboard()
    a, g, m, s, y, five = [kb.add_key(x) for x in "agmsy5"]
    space = kb.add_key("SPACE", text=" ")
    for k1, k2 in zip([a, g, m, s, y, five], [g, m, s, y, five, space]):
        kb.add_transition(k1, k2, "KEY_DOWN")

    page = SearchPage(dut, kb)
    page = page.enter_text(" ")
    assert page.selection.name == "SPACE"
    assert dut.entered == " "


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_navigate_to(dut, kb):
    page = SearchPage(dut, kb)
    assert page.selection.name == "a"
    page = page.navigate_to("CLEAR")
    assert page.selection.name == "CLEAR"
    assert dut.pressed == ["KEY_DOWN"] * 6 + ["KEY_RIGHT"] * 2


@pytest.mark.parametrize("kb", [kb1, kb2, kb5], ids=["kb1", "kb2", "kb5"])
def test_navigate_to_other_mode(dut, kb):
    page = SearchPage(dut, kb)
    assert page.selection.name == "a"
    assert page.selection.mode == "lowercase"
    page = page.navigate_to({"name": "CLEAR", "mode": "uppercase"})
    assert page.selection.name == "CLEAR"
    assert page.selection.mode == "uppercase"
    assert dut.pressed == ["KEY_UP", "KEY_RIGHT", "KEY_OK", "KEY_RIGHT"] + \
                          ["KEY_DOWN"] * 7


@pytest.mark.parametrize("target,verify_every_keypress,num_presses", [
    ("b", False, 1),
    ("b", True, 1),
    ("c", False, 2),
    ("c", True, 1),
])
@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_that_navigate_to_checks_target(double_keypress_dut, kb, target,
                                        verify_every_keypress, num_presses):
    """DUT skips the B when pressing right from A (and lands on C)."""
    page = SearchPage(double_keypress_dut, kb)
    assert page.selection.name == "a"
    with pytest.raises(AssertionError):
        page.navigate_to(target, verify_every_keypress, retries=0)
    assert double_keypress_dut.pressed == ["KEY_RIGHT"] * num_presses


def test_that_enter_text_retries_missed_keypresses(missed_keypress_dut):
    page = SearchPage(missed_keypress_dut, kb1)
    assert page.selection.name == "a"
    page = page.enter_text("bcecdfdadcfc", retries=100)
    #                       112212233133
    assert page.selection.name == "c"
    assert missed_keypress_dut.entered == "bcecdfdadcfc"


def test_that_navigate_to_retries_overshoot(double_keypress_dut):
    page = SearchPage(double_keypress_dut, kb1)
    assert page.selection.name == "a"
    page = page.navigate_to("b")
    assert page.selection.name == "b"
    assert double_keypress_dut.pressed == ["KEY_RIGHT", "KEY_LEFT"]


def test_that_navigate_to_waits_for_dut_to_catch_up(slow_dut):
    page = SearchPage(slow_dut, kb1)
    assert page.selection.name == "a"
    page = page.navigate_to("f")
    assert page.selection.name == "f"
    assert slow_dut.pressed == ["KEY_RIGHT"] * 5


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_that_keyboard_validates_the_targets_before_navigating(dut, kb):
    page = SearchPage(dut, kb)
    with pytest.raises(ValueError):
        page.enter_text("abcÑ")
    assert dut.pressed == []
    with pytest.raises(ValueError):
        page.navigate_to("Ñ")
    assert dut.pressed == []


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_that_keyboard_validates_the_page_object_selection(dut, kb):
    page = SearchPage(dut, kb, is_visible=False)
    with pytest.raises(AssertionError) as excinfo:
        page.navigate_to("a", page)
    assert "SearchPage page isn't visible" in str(excinfo.value)

    page = SearchPage(dut, kb, selection=None)
    with pytest.raises(AssertionError) as excinfo:
        page.navigate_to("a", page)
    assert "page.selection (None) isn't in the keyboard" in str(excinfo.value)


def test_that_navigate_to_doesnt_type_text_from_shift_transitions(dut):
    page = SearchPage(dut, kb4)
    dut.symbols_is_shift = True
    dut.mode = "uppercase"
    assert page.selection.name == "A"
    assert page.selection.mode == "uppercase"
    page = page.navigate_to("a")
    assert page.selection.name == "a"
    assert page.selection.mode == "lowercase"
    assert dut.entered == ""


def test_that_enter_text_recalculates_after_shift_transitions(dut):
    print(edgelists["uppercase"])
    page = SearchPage(dut, kb4)
    dut.symbols_is_shift = True
    assert page.selection.name == "a"
    assert page.selection.mode == "lowercase"
    page = page.enter_text("Aa")
    assert dut.entered == "Aa"
    assert dut.pressed == [
        "KEY_UP", "KEY_RIGHT", "KEY_RIGHT", "KEY_OK",  # shift
        "KEY_LEFT", "KEY_LEFT", "KEY_DOWN", "KEY_OK",  # A
        "KEY_OK"  # a
    ]


def test_edgelist_with_hash_sign():
    """Regression test. `networkx.parse_edgelist` treats "#" as a comment."""
    kb = stbt.Keyboard()
    kb.add_edgelist("""
        ### three hashes for a comment
        @hotmail.com !#$ KEY_DOWN
        @hotmail.com @ KEY_DOWN
        @ # KEY_RIGHT
        # @ KEY_LEFT
    """)
    hotmail = kb.find_key("@hotmail.com")
    symbols = kb.find_key("!#$")
    at_sign = kb.find_key("@")
    hash_sign = kb.find_key("#")
    assert list(_keys_to_press(kb.G, hotmail, [symbols])) == [
        ("KEY_DOWN", {at_sign, symbols})]
    assert list(_keys_to_press(kb.G, hotmail, [at_sign])) == [
        ("KEY_DOWN", {at_sign, symbols})]
    assert list(_keys_to_press(kb.G, at_sign, [hash_sign])) == [
        ('KEY_RIGHT', {hash_sign})]
    assert list(_keys_to_press(kb.G, hash_sign, [at_sign])) == [
        ('KEY_LEFT', {at_sign})]


def test_invalid_edgelist():
    kb = stbt.Keyboard()
    with pytest.raises(ValueError) as excinfo:
        kb.add_edgelist("""
            A B KEY_RIGHT
            B A
        """)
    assert "line 2" in str(excinfo.value)
    assert "'B A'" in str(excinfo.value)

    with pytest.raises(ValueError):
        kb.add_edgelist("""
            A B KEY_RIGHT toomanyfields
        """)

    kb.add_edgelist("")  # Doesn't raise


def test_that_add_key_infers_text():
    kb = stbt.Keyboard()
    a = kb.add_key("a")
    assert a.name == "a"
    assert a.text == "a"
    space = kb.add_key(" ")
    assert space.name == " "
    assert space.text == " "
    clear = kb.add_key("clear")
    assert clear.name == "clear"
    assert not clear.text


def test_that_add_grid_returns_grid_of_keys():
    kb = stbt.Keyboard()
    # The Disney+ search keyboard on Roku has an "accents" mode where some of
    # the keys are blank. You *can* navigate to them, but pressing OK has no
    # effect.
    grid = kb.add_grid(
        stbt.Grid(stbt.Region(x=265, y=465, right=895, bottom=690),
                  data=["àáâãäåæýÿš",
                        list("èéêëìíîžđ") + [""],
                        list("ïòóôõöøß") + ["", ""],
                        list("œùúûüçñ") + ["", "", ""]]))
    assert isinstance(grid[0].data, stbt.Keyboard.Key)

    right_neighbours = kb.add_grid(
        stbt.Grid(stbt.Region(x=915, y=465, right=1040, bottom=690),
                  data=[["CAPS LOCK"],
                        ["ABC123"],
                        ["!?#$%&"],
                        ["åéåøØ¡"]]))

    for i in range(4):
        kb.add_transition(grid[9, i].data, right_neighbours[0, i].data,
                          "KEY_RIGHT")

    assert [k for k, _ in
            _keys_to_press(kb.G, kb.find_key("ß"), [kb.find_key("!?#$%&")])] \
        == ["KEY_RIGHT"] * 3


def test_that_keyboard_catches_errors_at_definition_time():
    kb = stbt.Keyboard()

    # Can't add the same key twice:
    kb.add_key("a")
    with pytest.raises(ValueError) as excinfo:
        kb.add_key("a")
    assert_repr_equal(
        "Key already exists: Keyboard.Key(name='a', text='a', region=None, mode=None)",  # pylint:disable=line-too-long
        str(excinfo.value))

    # Can't add transition to key that doesn't exist:
    with pytest.raises(ValueError) as excinfo:
        kb.add_transition("a", "b", "KEY_RIGHT")
    assert_repr_equal("Query 'b' doesn't match any key in the keyboard",
                      str(excinfo.value))

    # ...but add_edgelist creates keys as needed:
    kb.add_edgelist("a b KEY_RIGHT")

    # All keys must have modes or none of them can
    kb.add_key(" ")
    with pytest.raises(ValueError) as excinfo:
        kb.add_key(" ", mode="uppercase")
    assert_repr_equal(
        "Key ...'name': ' '...'mode': 'uppercase'... specifies 'mode', but none of the other keys in the keyboard do",  # pylint:disable=line-too-long
        str(excinfo.value))

    # All keys must have regions or none of them can
    with pytest.raises(ValueError) as excinfo:
        kb.add_grid(stbt.Grid(
            region=stbt.Region(x=0, y=0, right=200, bottom=100),
            data=[["a", "b", "c", "d"]]))
    assert_repr_equal(
        "Key ...'a'... specifies 'region', but none of the other keys in the keyboard do",  # pylint:disable=line-too-long
        str(excinfo.value))

    # Can't add grid with no data:
    with pytest.raises(ValueError) as excinfo:
        kb.add_grid(stbt.Grid(
            region=stbt.Region(x=0, y=0, right=200, bottom=100),
            cols=6, rows=6))
    assert_repr_equal("Grid cell [0,0] doesn't have any data",
                      str(excinfo.value))

    # Now a keyboard with modes: #############################################
    kb = stbt.Keyboard()
    kb.add_key("a", mode="lowercase")
    kb.add_key("A", mode="uppercase")
    kb.add_key(" ", mode="lowercase")

    # All keys must have modes or none of them can
    with pytest.raises(ValueError) as excinfo:
        kb.add_key(" ")
    assert_repr_equal(
        "Key already exists: Keyboard.Key(name=' ', text=' ', region=None, mode='lowercase')",  # pylint:disable=line-too-long
        str(excinfo.value))
    with pytest.raises(ValueError) as excinfo:
        kb.add_key("b")
    assert_repr_equal(
        "Key ...'name': 'b'... doesn't specify 'mode', but all the other keys in the keyboard do",  # pylint:disable=line-too-long
        str(excinfo.value))

    # add_edgelist is happy as long as it can uniquely identify existing keys:
    kb.add_edgelist("a SPACE KEY_DOWN")

    # ...but if it's ambiguous, it's an error:
    kb.add_key(" ", mode="uppercase")
    with pytest.raises(ValueError) as excinfo:
        kb.add_edgelist("a SPACE KEY_DOWN")
    assert_repr_equal(
        "Ambiguous key {'name': ' '}: Could mean Keyboard.Key(name=' ', text=' ', region=None, mode='lowercase') or Keyboard.Key(name=' ', text=' ', region=None, mode='uppercase')",  # pylint:disable=line-too-long
        str(excinfo.value))

    # ...so we need to specify the mode explicitly:
    kb.add_edgelist("a SPACE KEY_DOWN", mode="lowercase")


def assert_repr_equal(a, b):
    a = re.escape(a).replace(r"\.\.\.", ".*")
    b = b.replace("u'", "'")
    assert re.match("^" + a + "$", b)


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_keys_to_press(kb):
    a = kb.find_key("a")
    b = kb.find_key("b")
    c = kb.find_key("c")
    g = kb.find_key("g")
    h = kb.find_key("h")
    five = kb.find_key("5", mode="lowercase" if kb.modes else None)
    six = kb.find_key("6", mode="lowercase" if kb.modes else None)
    space = kb.find_key(" ", mode="lowercase" if kb.modes else None)

    assert list(_keys_to_press(kb.G, a, [a])) == []
    assert list(_keys_to_press(kb.G, a, [b])) == [("KEY_RIGHT", {b})]
    assert list(_keys_to_press(kb.G, b, [a])) == [("KEY_LEFT", {a})]
    assert list(_keys_to_press(kb.G, a, [c])) == [("KEY_RIGHT", {b}),
                                                  ("KEY_RIGHT", {c})]
    assert list(_keys_to_press(kb.G, c, [a])) == [("KEY_LEFT", {b}),
                                                  ("KEY_LEFT", {a})]
    assert list(_keys_to_press(kb.G, a, [g])) == [("KEY_DOWN", {g})]
    assert list(_keys_to_press(kb.G, g, [a])) == [("KEY_UP", {a})]

    # I don't know which of these paths it will choose:
    assert list(_keys_to_press(kb.G, a, [h])) in (
        [("KEY_RIGHT", {b}), ("KEY_DOWN", {h})],
        [("KEY_DOWN", {g}), ("KEY_RIGHT", {h})])

    # Pressing UP from SPACE could land on 5 or 6, depending on previous state
    # (of the device-under-test) that isn't modelled by our Keyboard graph.
    assert list(_keys_to_press(kb.G, space, [five])) == [("KEY_UP",
                                                          {five, six})]

    if kb.modes:
        A = kb.find_key("A")
        B = kb.find_key("B")
        FIVE = kb.find_key("5", mode="uppercase")
        SPACE = kb.find_key(" ", mode="uppercase")

        # Changing modes:
        lowercase = kb.find_key("lowercase", mode="lowercase")
        LOWERCASE = kb.find_key("lowercase", mode="uppercase")
        uppercase = kb.find_key("uppercase", mode="lowercase")
        UPPERCASE = kb.find_key("uppercase", mode="uppercase")
        assert list(_keys_to_press(kb.G, a, [A])) == [
            ("KEY_UP", {lowercase}),
            ("KEY_RIGHT", {uppercase}),
            ("KEY_OK", {UPPERCASE}),
            ("KEY_LEFT", {LOWERCASE}),
            ("KEY_DOWN", {A, B})]

        # Navigate to nearest key:
        assert list(_keys_to_press(kb.G, FIVE, [space, SPACE])) == [
            ("KEY_DOWN", {SPACE})]
        assert list(_keys_to_press(kb.G, five, [space, SPACE])) == [
            ("KEY_DOWN", {space})]


@pytest.mark.parametrize("kb", [kb1, kb2, kb3, kb5],
                         ids=["kb1", "kb2", "kb3", "kb5"])
def test_keyboard_weights(kb):
    five = kb.find_key("5", mode="lowercase" if kb.modes else None)
    six = kb.find_key("6", mode="lowercase" if kb.modes else None)
    space = kb.find_key(" ", mode="lowercase" if kb.modes else None)
    backspace = kb.find_key("BACKSPACE", mode="lowercase" if kb.modes else None)
    assert kb.G[five][space].get("weight") is None
    assert kb.G[six][space].get("weight") is None
    assert kb.G[space][five]["weight"] == 100
    assert kb.G[space][six]["weight"] == 100
    assert kb.G[space][backspace].get("weight") is None
    assert kb.G[backspace][space].get("weight") is None


def test_that_we_need_add_weight():
    from networkx.algorithms.shortest_paths.generic import shortest_path

    # W X Y Z
    #  SPACE
    kb = stbt.Keyboard()
    W = kb.add_key("W")
    X = kb.add_key("X")
    Y = kb.add_key("Y")
    Z = kb.add_key("Z")
    SPACE = kb.add_key(" ")
    for k in [W, X, Y, Z]:
        kb.add_transition(k, SPACE, "KEY_DOWN")
    for k1, k2 in zip([W, X, Y], [X, Y, Z]):
        kb.add_transition(k1, k2, "KEY_RIGHT")

    # This is the bug:
    assert shortest_path(kb.G, W, Z) == [W, SPACE, Z]
    # And this is how we fix it:
    assert shortest_path(kb.G, W, Z, weight="weight") == [W, X, Y, Z]

    assert [k for k, _ in _keys_to_press(kb.G, W, [Z])] == ["KEY_RIGHT"] * 3


def test_strip_shift_transitions():
    for kb in [kb1, kb2, kb3]:
        G_ = _strip_shift_transitions(kb.G)
        assert sorted(G_.nodes()) == sorted(kb.G.nodes())
        assert sorted(G_.edges(data=True)) == sorted(kb.G.edges(data=True))

    G_ = _strip_shift_transitions(kb4.G)
    assert sorted(G_.nodes()) == sorted(kb4.G.nodes())
    assert sorted(G_.edges(data=True)) != sorted(kb4.G.edges(data=True))
    assert len(G_.edges(data=True)) == len(kb4.G.edges(data=True)) - len(
        "abcdefghijklmnopqrstuvwxyz1234567890")


def test_channel4_keyboard():
    REGION = stbt.Region(50, 166, right=1235, bottom=242)

    LOWERCASE = stbt.Grid(
        stbt.Region(66, 182, right=1226, bottom=228),
        data=[["123"] * 2 + [" "] * 2 + list("abcdefghijklmnopqrstuvwxyz") +
              ["BACKSPACE"] * 2])
    NUMBERS = stbt.Grid(
        stbt.Region(357, 180, right=934, bottom=228),
        data=[["#+="] * 2 + [" "] * 2 + list("1234567890") + ["BACKSPACE"] * 2])
    SYMBOLS = stbt.Grid(
        stbt.Region(x=35, y=179, right=1235, bottom=228),
        data=[["abc"] * 2 + [" "] * 3 +
              list("`'\";:~=*+-_,.?!@#$%^&|/\\()[]{}<>") + ["BACKSPACE"] * 2])

    KEYBOARD = stbt.Keyboard(mask=REGION)

    KEYBOARD.add_grid(LOWERCASE, mode="lowercase", merge=True)
    KEYBOARD.add_grid(NUMBERS, mode="numbers", merge=True)
    KEYBOARD.add_grid(SYMBOLS, mode="symbols", merge=True)

    # It's difficult to tell which key we'll land on when we press KEY_PLAY,
    # so we add transitions from every key to every other key according to the
    # mode.
    for source_mode, target_mode in [
        ("lowercase", "numbers"),
        ("numbers", "symbols"),
        ("symbols", "lowercase"),
    ]:
        for source in KEYBOARD.find_keys(mode=source_mode):
            for target in KEYBOARD.find_keys(mode=target_mode):
                KEYBOARD.add_transition(
                    source=source, target=target,
                    keypress="KEY_PLAY", symmetrical=False)

    targets = KEYBOARD.find_keys("BACKSPACE")
    current = KEYBOARD.find_key("#+=")
    keys = [x[0] for x in _keys_to_press(KEYBOARD.G, current, targets)]
    assert keys == ["KEY_RIGHT"] * 12


def test_disjoint_modes():
    # The Channel 4 app has a grid-like keyboard on one of my Apple TVs (4K 1st
    # gen) and a single row on my other Apple TV (4k 3rd gen), despite having
    # the same tvOS version and app version. I have a single Page Object that
    # recognises both appearances, and models the keyboard as having 2 disjoint
    # modes (that is, there's no way to get from one mode to the other).
    kb = stbt.Keyboard()
    kb.add_grid(
        stbt.Grid(stbt.Region(0, 0, 200, 200), data=[
            ["a", "b", "c", "d", "e", "f"],
            ["g", "h", "i", "j", "k", "l"],
            ["m", "n", "o", "p", "q", "r"],
            ["s", "t", "u", "v", "w", "x"],
            ["y", "z", "1", "2", "3", "4"],
            ["5", "6", "7", "8", "9", "0"]]),
        mode="grid")
    kb.add_grid(
        stbt.Grid(stbt.Region(0, 0, 1280, 50),
                  data=["abcdefghijklmnopqrstuvwxyz"]),
        mode="single-row")

    keys = [x[0] for x in _keys_to_press(kb.G,
                                         kb.find_key("a", mode="grid"),
                                         kb.find_keys("g"))]
    assert keys == ["KEY_DOWN"]

    keys = [x[0] for x in _keys_to_press(kb.G,
                                         kb.find_key("a", mode="single-row"),
                                         kb.find_keys("g"))]
    assert keys == ["KEY_RIGHT"] * 6

    with pytest.raises(NetworkXNoPath, match=(
            r"No path to Keyboard\.Key\(name='0', text='0', "
            r"region=Region\(.*\), mode='grid'\)\.")):
        list(_keys_to_press(kb.G,
                            kb.find_key("a", mode="single-row"),
                            kb.find_keys("0")))


@pytest.mark.skipif("STBT_RUN_PERFORMANCE_TESTS" not in os.environ,
                    reason="$STBT_RUN_PERFORMANCE_TESTS is not set")
def test_keyboard_definition_performance():
    start_time = time.time()
    kb = stbt.Keyboard()
    for mode in range(100):
        kb.add_grid(stbt.Grid(region=stbt.Region(0, 0, 26, 1),
                              data=["abcdefghijklmnopqrstuvwxyz"]),
                    mode=str(mode))
    duration = time.time() - start_time
    assert duration < 0.3
