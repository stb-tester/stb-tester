from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import networkx as nx
import mock
import pytest

from stbt.keyboard import Keyboard, _add_weights, _keys_to_press
from _stbt.transition import _TransitionResult, TransitionStatus


YOUTUBE_SEARCH_KEYBOARD = """
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
G = nx.parse_edgelist(YOUTUBE_SEARCH_KEYBOARD.split("\n"),
                      create_using=nx.DiGraph,
                      data=[("key", str)])
nx.relabel_nodes(G, {"SPACE": " "}, copy=False)


def test_keys_to_press():
    assert list(_keys_to_press(G, "A", "A")) == []
    assert list(_keys_to_press(G, "A", "B")) == ["KEY_RIGHT"]
    assert list(_keys_to_press(G, "B", "A")) == ["KEY_LEFT"]
    assert list(_keys_to_press(G, "A", "C")) == ["KEY_RIGHT", "KEY_RIGHT"]
    assert list(_keys_to_press(G, "C", "A")) == ["KEY_LEFT", "KEY_LEFT"]
    assert list(_keys_to_press(G, "A", "H")) == ["KEY_DOWN"]
    assert list(_keys_to_press(G, "H", "A")) == ["KEY_UP"]
    assert list(_keys_to_press(G, "A", "I")) in (["KEY_RIGHT", "KEY_DOWN"],
                                                 ["KEY_DOWN", "KEY_RIGHT"])
    assert list(_keys_to_press(G, " ", "A")) == ["KEY_UP"]


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
        create_using=nx.DiGraph,
        data=[("key", str)])

    # This is the bug:
    assert nx.shortest_path(G, "W", "Z") == ["W", "SPACE", "Z"]

    # And this is how we fix it:
    _add_weights(G)
    assert nx.shortest_path(G, "W", "Z", weight="weight") == [
        "W", "X", "Y", "Z"]


class YouTubeKeyboard(object):
    """PageObject that mocks out stbt.get_frame() for testing."""
    def __init__(self):
        self._frame = None
        self.is_visible = True
        self.selection = "A"
        self.actual_state = "A"
        self.entered = ""
        # Pressing up from SPACE returns to the last letter we were at:
        self.prev_state = "A"

    def refresh(self):
        self.selection = self.actual_state
        return self

    def enter_text(self, text):
        kb = Keyboard(self, YOUTUBE_SEARCH_KEYBOARD, navigate_timeout=0.1)
        kb.enter_text(text.upper())

    def press(self, key):
        print("Pressed %s" % key)
        if key == "KEY_OK":
            self.entered += self.actual_state
        else:
            next_states = [
                t for _, t, k in G.edges(self.actual_state, data="key")
                if k == key]
            if self.prev_state in next_states:
                next_state = self.prev_state
            else:
                next_state = next_states[0]
            if self.actual_state not in (" ", "CLEAR", "SEARCH"):
                self.prev_state = self.actual_state
            self.actual_state = next_state

    def press_and_wait(self, key, mask):  # pylint:disable=unused-argument
        self.press(key)
        return _TransitionResult(None, TransitionStatus.COMPLETE, 0, 0, 0)


@pytest.fixture(scope="function")
def youtubekeyboard():
    kb = YouTubeKeyboard()
    with mock.patch("stbt.press", kb.press), \
            mock.patch("stbt.press_and_wait", kb.press_and_wait):
        yield kb


def test_enter_text(youtubekeyboard):  # pylint:disable=redefined-outer-name
    assert youtubekeyboard.selection == "A"
    youtubekeyboard.enter_text("hi there")
    assert youtubekeyboard.entered == "HI THERE"
    assert youtubekeyboard.selection == "E"
