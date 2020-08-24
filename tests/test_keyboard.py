# coding: utf-8

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import sys

import networkx as nx
import numpy
import pytest

try:
    from unittest import mock
except ImportError:
    import mock  # Python 2 backport

import stbt_core as stbt
from _stbt.keyboard import _add_weights, _keys_to_press
from _stbt.transition import _TransitionResult, TransitionStatus


GRAPH = """
    A B KEY_RIGHT
    A H KEY_DOWN
    B A KEY_LEFT
    B C KEY_RIGHT
    B I KEY_DOWN
    C B KEY_LEFT
    C D KEY_RIGHT
    C J KEY_DOWN
    D C KEY_LEFT
    D E KEY_RIGHT
    D K KEY_DOWN
    E D KEY_LEFT
    E F KEY_RIGHT
    E L KEY_DOWN
    F E KEY_LEFT
    F G KEY_RIGHT
    F M KEY_DOWN
    G F KEY_LEFT
    G N KEY_DOWN
    H I KEY_RIGHT
    H A KEY_UP
    H O KEY_DOWN
    I H KEY_LEFT
    I J KEY_RIGHT
    I B KEY_UP
    I P KEY_DOWN
    J I KEY_LEFT
    J K KEY_RIGHT
    J C KEY_UP
    J Q KEY_DOWN
    K J KEY_LEFT
    K L KEY_RIGHT
    K D KEY_UP
    K R KEY_DOWN
    L K KEY_LEFT
    L M KEY_RIGHT
    L E KEY_UP
    L S KEY_DOWN
    M L KEY_LEFT
    M N KEY_RIGHT
    M F KEY_UP
    M T KEY_DOWN
    N M KEY_LEFT
    N G KEY_UP
    N U KEY_DOWN
    O P KEY_RIGHT
    O H KEY_UP
    O V KEY_DOWN
    P O KEY_LEFT
    P Q KEY_RIGHT
    P I KEY_UP
    P W KEY_DOWN
    Q P KEY_LEFT
    Q R KEY_RIGHT
    Q J KEY_UP
    Q X KEY_DOWN
    R Q KEY_LEFT
    R S KEY_RIGHT
    R K KEY_UP
    R Y KEY_DOWN
    S R KEY_LEFT
    S T KEY_RIGHT
    S L KEY_UP
    S Z KEY_DOWN
    T S KEY_LEFT
    T U KEY_RIGHT
    T M KEY_UP
    T - KEY_DOWN
    U T KEY_LEFT
    U N KEY_UP
    U ' KEY_DOWN
    V W KEY_RIGHT
    V O KEY_UP
    V SPACE KEY_DOWN
    W V KEY_LEFT
    W X KEY_RIGHT
    W P KEY_UP
    W SPACE KEY_DOWN
    X W KEY_LEFT
    X Y KEY_RIGHT
    X Q KEY_UP
    X SPACE KEY_DOWN
    Y X KEY_LEFT
    Y Z KEY_RIGHT
    Y R KEY_UP
    Y SPACE KEY_DOWN
    Z Y KEY_LEFT
    Z - KEY_RIGHT
    Z S KEY_UP
    Z SPACE KEY_DOWN
    - Z KEY_LEFT
    - ' KEY_RIGHT
    - T KEY_UP
    - SPACE KEY_DOWN
    ' - KEY_LEFT
    ' U KEY_UP
    ' SPACE KEY_DOWN
    SPACE CLEAR KEY_RIGHT
    SPACE V KEY_UP
    SPACE W KEY_UP
    SPACE X KEY_UP
    SPACE Y KEY_UP
    SPACE Z KEY_UP
    SPACE - KEY_UP
    SPACE ' KEY_UP
    CLEAR SPACE KEY_LEFT
    CLEAR SEARCH KEY_RIGHT
    CLEAR V KEY_UP
    CLEAR W KEY_UP
    CLEAR X KEY_UP
    CLEAR Y KEY_UP
    CLEAR Z KEY_UP
    CLEAR - KEY_UP
    CLEAR ' KEY_UP
    SEARCH CLEAR KEY_LEFT
    SEARCH V KEY_UP
    SEARCH W KEY_UP
    SEARCH X KEY_UP
    SEARCH Y KEY_UP
    SEARCH Z KEY_UP
    SEARCH - KEY_UP
    SEARCH ' KEY_UP
"""
G = stbt.Keyboard.parse_edgelist(GRAPH)

if sys.version_info.major == 2:
    G_BYTES = stbt.Keyboard.parse_edgelist(GRAPH.encode('utf-8'))
    GRAPHS = [G, G_BYTES]
else:
    GRAPHS = [G]


@pytest.mark.parametrize("g", GRAPHS)
def test_keys_to_press(g):
    assert list(_keys_to_press(g, "A", "A")) == []
    assert list(_keys_to_press(g, "A", "B")) == [("KEY_RIGHT", {"B"})]
    assert list(_keys_to_press(g, "B", "A")) == [("KEY_LEFT", {"A"})]
    assert list(_keys_to_press(g, "A", "C")) == [("KEY_RIGHT", {"B"}),
                                                 ("KEY_RIGHT", {"C"})]
    assert list(_keys_to_press(g, "C", "A")) == [("KEY_LEFT", {"B"}),
                                                 ("KEY_LEFT", {"A"})]
    assert list(_keys_to_press(g, "A", "H")) == [("KEY_DOWN", {"H"})]
    assert list(_keys_to_press(g, "H", "A")) == [("KEY_UP", {"A"})]
    assert list(_keys_to_press(g, "A", "I")) in (
        [("KEY_RIGHT", {"B"}), ("KEY_DOWN", {"I"})],
        [("KEY_DOWN", {"H"}), ("KEY_RIGHT", {"I"})])
    assert list(_keys_to_press(g, " ", "A")) == [
        ("KEY_UP", {"V", "W", "X", "Y", "Z", "-", "'"})]


def test_add_weights():
    G = nx.parse_edgelist(  # pylint:disable=redefined-outer-name
        """ W SPACE KEY_DOWN
            X SPACE KEY_DOWN
            Y SPACE KEY_DOWN
            Z SPACE KEY_DOWN
            SPACE W KEY_UP
            SPACE X KEY_UP
            SPACE Y KEY_UP
            SPACE Z KEY_UP
            W X KEY_RIGHT
            X Y KEY_RIGHT
            Y Z KEY_RIGHT""".split("\n"),
        create_using=nx.DiGraph(),
        data=[("key", str)])

    # This is the bug:
    assert nx.shortest_path(G, "W", "Z") == ["W", "SPACE", "Z"]

    # And this is how we fix it:
    _add_weights(G)
    assert nx.shortest_path(G, "W", "Z", weight="weight") == [
        "W", "X", "Y", "Z"]


class _Keyboard(stbt.FrameObject):
    """Immutable FrameObject representing the test's view of the Device Under
    Test (``dut``).

    The keyboard looks like this::

        A  B  C  D  E  F  G
        H  I  J  K  L  M  N
        O  P  Q  R  S  T  U
        V  W  X  Y  Z  -  '
         SPACE  CLEAR  SEARCH

    """
    def __init__(self, dut):
        super(_Keyboard, self).__init__(
            frame=numpy.zeros((720, 1280, 3), dtype=numpy.uint8))
        self._dut = dut  # Device Under Test -- i.e. ``YouTubeKeyboard``
        self._selection = self._dut.selection

    @property
    def is_visible(self):
        return True

    @property
    def selection(self):
        return self._selection

    def refresh(self, frame=None, **kwargs):
        print("_Keyboard.refresh: Now on %r" % self._dut.selection)
        return _Keyboard(dut=self._dut)

    KEYBOARD = stbt.Keyboard(GRAPH, navigate_timeout=0.1)

    def enter_text(self, text):
        return self.KEYBOARD.enter_text(text.upper(), page=self)

    def navigate_to(self, target, verify_every_keypress=False):
        return self.KEYBOARD.navigate_to(
            target, page=self, verify_every_keypress=verify_every_keypress)


class YouTubeKeyboard(object):
    """Fake keyboard implementation for testing."""

    def __init__(self):
        self.selection = "A"
        self.page = _Keyboard(dut=self)
        self.pressed = []
        self.entered = ""
        # Pressing up from SPACE returns to the last letter we were at:
        self.prev_state = "A"

    def press(self, key):
        print("Pressed %s" % key)
        self.pressed.append(key)
        if key == "KEY_OK":
            self.entered += self.selection
        else:
            next_states = [
                t for _, t, k in G.edges(self.selection, data="key")
                if k == key]
            if self.prev_state in next_states:
                next_state = self.prev_state
            else:
                next_state = next_states[0]
            if self.selection not in (" ", "CLEAR", "SEARCH"):
                self.prev_state = self.selection
            self.selection = next_state

    def press_and_wait(self, key, **kwargs):  # pylint:disable=unused-argument
        self.press(key)
        return _TransitionResult(key, None, TransitionStatus.COMPLETE, 0, 0, 0)


class BuggyKeyboard(YouTubeKeyboard):
    def press(self, key):
        super(BuggyKeyboard, self).press(key)
        if key == "KEY_RIGHT" and self.selection == "B":
            self.selection = "C"


@pytest.fixture(scope="function")
def youtubekeyboard():
    kb = YouTubeKeyboard()
    with mock.patch("stbt_core.press", kb.press), \
            mock.patch("stbt_core.press_and_wait", kb.press_and_wait):
        yield kb


@pytest.fixture(scope="function")
def buggykeyboard():
    """Pressing KEY_RIGHT from A skips over B and lands on C.

    Note that the model we specify in our test-scripts still thinks that
    KEY_RIGHT should land on B. This simulates a bug in the device-under-test,
    not in the test-scripts.
    """
    kb = BuggyKeyboard()
    with mock.patch("stbt_core.press", kb.press), \
            mock.patch("stbt_core.press_and_wait", kb.press_and_wait):
        yield kb


def test_enter_text(youtubekeyboard):  # pylint:disable=redefined-outer-name
    page = youtubekeyboard.page
    assert page.selection == "A"
    page = page.enter_text("hi there")
    assert page.selection == "E"
    assert youtubekeyboard.entered == "HI THERE"


def test_that_enter_text_uses_minimal_keypresses(youtubekeyboard):  # pylint:disable=redefined-outer-name
    page = youtubekeyboard.page
    assert page.selection == "A"
    page.enter_text("HI")
    assert youtubekeyboard.pressed == ["KEY_DOWN", "KEY_OK",
                                       "KEY_RIGHT", "KEY_OK"]


def test_that_keyboard_validates_the_targets(youtubekeyboard):  # pylint:disable=redefined-outer-name
    page = youtubekeyboard.page
    with pytest.raises(ValueError):
        page.enter_text("ABCÑ")
    assert youtubekeyboard.pressed == []
    with pytest.raises(ValueError):
        page.navigate_to("Ñ")
    assert youtubekeyboard.pressed == []


def test_navigate_to(youtubekeyboard):  # pylint:disable=redefined-outer-name
    page = youtubekeyboard.page
    assert page.selection == "A"
    page = page.navigate_to("SEARCH")
    assert page.selection == "SEARCH"
    assert youtubekeyboard.pressed == ["KEY_DOWN"] * 4 + ["KEY_RIGHT"] * 2


@pytest.mark.parametrize("target,verify_every_keypress,num_presses", [
    ("B", False, 1),
    ("B", True, 1),
    ("C", False, 2),
    ("C", True, 1),
])
def test_that_navigate_to_checks_target(
        buggykeyboard, target, verify_every_keypress, num_presses):  # pylint:disable=redefined-outer-name
    """buggykeyboard skips the B when pressing right from A (and lands on C)."""
    page = buggykeyboard.page
    assert page.selection == "A"
    with pytest.raises(AssertionError):
        page.navigate_to(target, verify_every_keypress)
    assert buggykeyboard.pressed == ["KEY_RIGHT"] * num_presses


def test_composing_complex_keyboards():
    """The YouTube keyboard on Roku looks like this::

        A  B  C  D  E  F  G
        H  I  J  K  L  M  N
        O  P  Q  R  S  T  U
        V  W  X  Y  Z  -  '
         SPACE  CLEAR  SEARCH

    The first 4 rows behave normally within themselves. The bottom row behaves
    normally within itself. But navigating to or from the bottom row is a bit
    irregular: No matter what column you're in, when you press KEY_DOWN you
    always land on SPACE. Then when you press KEY_UP, you go back to the column
    you were last on -- even if you had pressed KEY_RIGHT/KEY_LEFT to move
    within the bottom row. It's almost like they're two separate state
    machines, and we can model them as such, with a few explicit connections
    between the two.
    """
    letters = stbt.Grid(stbt.Region(x=540, y=100, right=840, bottom=280),
                        data=["ABCDEFG",
                              "HIJKLMN",
                              "OPQRSTU",
                              "VWXYZ-'"])
    space_row = stbt.Grid(stbt.Region(x=540, y=280, right=840, bottom=330),
                          data=[[" ", "CLEAR", "SEARCH"]])

    # Technique #0: Write the entire edgelist manually (as per previous tests)
    K0 = stbt.Keyboard(GRAPH)

    # Technique #1: Manipulate the graph (manually or programmatically) directly
    G1 = nx.compose(stbt.grid_to_navigation_graph(letters),
                    stbt.grid_to_navigation_graph(space_row))
    # Pressing down from the bottom row always goes to SPACE:
    for k in letters.data[-1]:
        G1.add_edge(k, " ", key="KEY_DOWN")
    # Pressing back up from the space/clear/search row can go to any column
    # in the bottom row:
    for k in space_row.data[0]:
        for j in letters.data[-1]:
            G1.add_edge(k, j, key="KEY_UP")
    K1 = stbt.Keyboard(G1)

    assert sorted(K0.G.edges(data=True)) == sorted(K1.G.edges(data=True))

    # Technique #2: Use manually-written edgelist only for the irregular edges
    # Note that `Keyboard.parse_edgelist` will normalise "SPACE" -> " " so all
    # 3 graphs will have the same representation for space: " ".
    connections = stbt.Keyboard.parse_edgelist("""
        V SPACE KEY_DOWN
        W SPACE KEY_DOWN
        X SPACE KEY_DOWN
        Y SPACE KEY_DOWN
        Z SPACE KEY_DOWN
        - SPACE KEY_DOWN
        ' SPACE KEY_DOWN
        SPACE V KEY_UP
        SPACE W KEY_UP
        SPACE X KEY_UP
        SPACE Y KEY_UP
        SPACE Z KEY_UP
        SPACE - KEY_UP
        SPACE ' KEY_UP
        CLEAR V KEY_UP
        CLEAR W KEY_UP
        CLEAR X KEY_UP
        CLEAR Y KEY_UP
        CLEAR Z KEY_UP
        CLEAR - KEY_UP
        CLEAR ' KEY_UP
        SEARCH V KEY_UP
        SEARCH W KEY_UP
        SEARCH X KEY_UP
        SEARCH Y KEY_UP
        SEARCH Z KEY_UP
        SEARCH - KEY_UP
        SEARCH ' KEY_UP
    """)
    G2 = nx.compose_all([stbt.grid_to_navigation_graph(letters),
                         stbt.grid_to_navigation_graph(space_row),
                         connections])
    K2 = stbt.Keyboard(G2)

    assert sorted(K0.G.edges(data=True)) == sorted(K2.G.edges(data=True))


def test_keyboard_with_hash_sign():
    """Regression test. `networkx.parse_edgelist` treats "#" as a comment."""
    kb = stbt.Keyboard("""
        ### three hashes for a comment
        @hotmail.com !#$ KEY_DOWN
        @hotmail.com @ KEY_DOWN
        @ # KEY_RIGHT
        # @ KEY_LEFT
        L K KEY_LEFT
        K L KEY_RIGHT
    """)
    keys = list(_keys_to_press(kb.G, "@hotmail.com", "@"))
    assert keys == [('KEY_DOWN', {'@', '!#$'})]

    assert list(_keys_to_press(kb.G, "@", "#")) == [('KEY_RIGHT', {'#'})]
    assert list(_keys_to_press(kb.G, "#", "@")) == [('KEY_LEFT', {'@'})]

    # L is the first character of the random comments delimiter in
    # `Keyboard.parse_edgelist`. Check that networkx uses the whole string, not
    # just the first character.
    assert list(_keys_to_press(kb.G, "K", "L")) == [('KEY_RIGHT', {'L'})]
    assert list(_keys_to_press(kb.G, "L", "K")) == [('KEY_LEFT', {'K'})]


def test_invalid_edgelist():
    with pytest.raises(ValueError) as excinfo:
        stbt.Keyboard("""
            A B KEY_RIGHT
            B A
        """)
    assert "line 2" in str(excinfo.value)
    assert "'B A'" in str(excinfo.value)

    with pytest.raises(ValueError):
        stbt.Keyboard("""
            A B KEY_RIGHT toomanyfields
        """)

    stbt.Keyboard("")  # Doesn't raise
