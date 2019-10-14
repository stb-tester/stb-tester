# coding: utf-8
"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import time
from collections import namedtuple
from logging import getLogger

import networkx as nx
import numpy
import stbt
from _stbt.utils import text_type


log = getLogger("stbt.keyboard")


class Keyboard(object):
    """Helper for navigating an on-screen keyboard using the remote control.

    You customize for the appearance & behaviour of the keyboard you're testing
    by specifying two things:

    * A `Page Object`_ that can tell you which key is currently selected on the
      screen. See the ``page`` parameter to ``enter_text`` and ``navigate_to``,
      below.

    * A `Directed Graph`_ that specifies the navigation between every key on
      the keyboard (for example on a qwerty keyboard: when Q is selected,
      pressing KEY_RIGHT on the remote control goes to W, and so on). See the
      ``graph`` parameter below.

    The constructor takes the following parameters:

    :type graph: str or networkx.DiGraph
    :param graph: A specification of the complete navigation graph (state
        machine) between adjacent keys, as a multiline string where each line
        is in the format ``<start_node> <end_node> <action>``. For example, the
        specification for a qwerty keyboard might look like this::

            '''
            Q W KEY_RIGHT
            Q A KEY_DOWN
            W Q KEY_LEFT
            <etc>
            '''

        For nodes that enter a character, use that character as the node name.
        For the space-bar use SPACE. For other nodes that don't enter a
        character when pressed, use a descriptive name such as CLEAR or ENTER
        (these nodes won't be used by ``enter_text`` but you can use them as a
        target of ``navigate_to``).

        On some keyboards, buttons like the space-bar are wider than other
        buttons and the navigation away from the button depends on the previous
        state. Our ``graph`` can't model this state, so specify all the
        possible transitions from the button. For example, on a qwerty
        keyboard::

            SPACE C KEY_UP
            SPACE V KEY_UP
            SPACE B KEY_UP
            SPACE N KEY_UP
            SPACE M KEY_UP

        For advanced users: instead of a string, ``graph`` can be a
        `networkx.DiGraph` where each edge has an attribute called ``key`` with
        a value like ``"KEY_RIGHT"``. If your keyboard's buttons are positioned
        in a regular grid, you can use `stbt.grid_to_navigation_graph` to
        generate this graph (or part of the graph, and then you can add any
        irregular connections explicitly with `networkx.DiGraph.add_edge`).
        See also `Keyboard.parse_edgelist`.

    :type mask: str or `numpy.ndarray`
    :param str mask:
        A mask to use when calling `stbt.press_and_wait` to determine when the
        current selection has finished moving. If the search page has a
        blinking cursor you need to mask out the region where the cursor can
        appear, as well as any other regions with dynamic content (such as a
        picture-in-picture with live TV). See `stbt.press_and_wait` for more
        details about the mask.

    :type navigate_timeout: int or float
    :param navigate_timeout: Timeout (in seconds) for ``navigate_to``. In
        practice ``navigate_to`` should only time out if you have a bug in your
        ``graph`` state machine specification.

    .. _Page Object: https://stb-tester.com/manual/object-repository#what-is-a-page-object
    .. _Directed Graph: https://en.wikipedia.org/wiki/Directed_graph
    """

    class Selection(namedtuple("Selection", "text region")):
        """Type that your Page Object's ``selection`` property can return.

        Has two attributes:

        * ``text`` (*str*) — The selected letter or button.
        * ``region`` (`stbt.Region`) — The position on screen of the selection /
          highlight.

        Is falsey if ``text`` and ``region`` are both ``None``.
        """

        def __bool__(self):
            return self.text is not None or self.region is not None

    def __init__(self, graph, mask=None, navigate_timeout=20):
        if isinstance(graph, nx.DiGraph):
            self.G = graph
        else:
            self.G = Keyboard.parse_edgelist(graph)
        try:
            nx.relabel_nodes(self.G, {"SPACE": " "}, copy=False)
        except KeyError:  # Node SPACE is not in the graph
            pass
        _add_weights(self.G)

        self.mask = None
        if isinstance(mask, numpy.ndarray):
            self.mask = mask
        elif mask:
            self.mask = stbt.load_image(mask)

        self.navigate_timeout = navigate_timeout

    # pylint:disable=fixme
    # TODO: case sensitive keyboards
    #   Caps lock can be supported with a graph like this:
    #       A CAPSLOCK_OFF KEY_LEFT
    #       CAPSLOCK_OFF CAPSLOCK_ON KEY_OK
    #       CAPSLOCK_ON a KEY_RIGHT
    #       a q KEY_UP
    #       <etc>
    #   (Other mode changes like ABC -> 123!@# can be supported in the same
    #   way.)
    #
    #   I don't know how best to support SHIFT (temporary mode change):
    #   - In shifted state KEY_OK will go from "A" to "a". We'd want to use
    #     press_and_wait before we check the new state. But...
    #   - In non-shifted state KEY_OK just enters the letter; the screen doesn't
    #     change otherwise. Currently we don't use press_and_wait here because
    #     typically the text-box where the text appears is masked out (because
    #     some UIs have a blinking cursor there) and there is no change anywhere
    #     else on the screen.
    #
    # TODO: Check that KEY_OK adds to the search text? With a property on the
    #   page object? OCR might be too unreliable for incomplete words. We don't
    #   use press_and_wait because the text-box might be masked out (some UIs
    #   have a blinking cursor there).

    def enter_text(self, text, page, verify_every_keypress=False):
        """Enter the specified text using the on-screen keyboard.

        :param str text: The text to enter. If your keyboard only supports a
            single case then you need to convert the text to uppercase or
            lowercase, as appropriate, before passing it to this method.

        :param stbt.FrameObject page: An instance of a `stbt.FrameObject`
            sub-class that describes the appearance of the on-screen keyboard.
            It must implement the following:

            * ``selection`` (*str* or `Keyboard.Selection`) — property that
              returns the name of the currently selected character (for example
              "A" or " ") or button (for example "CLEAR" or "SEARCH"). This
              property can return a string, or an object with a ``text``
              attribute that is a string.

              For grid-shaped keyboards, you can implement this property using
              `stbt.Grid` to map from the region of the selection (highlight)
              to the corresponding letter; see the example below.

            The ``page`` instance that you provide must represent the current
            state of the device-under-test.

        :param bool verify_every_keypress:
            If True, we will read the selected key after every keypress and
            assert that it matches the model (``graph``). If False (the
            default) we will only verify the selected key corresponding to each
            of the characters in ``text``. For example: to get from Q to D on a
            qwerty keyboard you need to press KEY_DOWN, KEY_RIGHT, KEY_RIGHT.
            The default behaviour will only verify that the selected key is D
            after pressing KEY_RIGHT the last time. This is faster, and closer
            to the way a human uses the on-screen keyboard.

            Set this to True to help debug your model if ``enter_text`` is
            behaving incorrectly.

        Typically your FrameObject will provide its own ``enter_text`` method,
        so your test scripts won't call this ``Keyboard`` class directly. For
        example::

            class YouTubeSearch(stbt.FrameObject):
                _kb = stbt.Keyboard('''
                    A B KEY_RIGHT
                    ...etc...
                    ''')
                letters = stbt.Grid(region=...,
                                    data=["ABCDEFG",
                                          "HIJKLMN",
                                          "OPQRSTU",
                                          "VWXYZ-'"])
                space_row = stbt.Grid(region=...,
                                      data=[[" ", "CLEAR", "SEARCH"]])

                @property
                def is_visible(self):
                    ...  # implementation not shown

                @property
                def selection(self):
                    m = stbt.match("keyboard-selection.png", frame=self._frame)
                    if not m:
                        return stbt.Keyboard.Selection(None, None)
                    try:
                        text = self.letters.get(region=m.region).data
                    except IndexError:
                        text = self.space_row.get(region=m.region).data
                    return stbt.Keyboard.Selection(text, m.region)

                def enter_text(self, text):
                    page = self
                    page = self._kb.enter_text(text.upper(), page)
                    self._kb.navigate_to("SEARCH", page)
                    stbt.press("KEY_OK")

                def navigate_to(self, target):
                    return self._kb.navigate_to(target, page=self)
        """

        for letter in text:
            if letter not in self.G:
                raise ValueError("'%s' isn't in the keyboard" % (letter,))

        for letter in text:
            page = self.navigate_to(letter, page, verify_every_keypress)
            stbt.press("KEY_OK")
        return page

    def navigate_to(self, target, page, verify_every_keypress=False):
        """Move the selection to the specified character.

        Note that this won't press KEY_OK on the target, it only moves the
        selection there.

        :param str target: The key or button to navigate to, for example "A",
            " ", or "CLEAR".
        :param stbt.FrameObject page: See ``enter_text``.
        :param bool verify_every_keypress: See ``enter_text``.

        :returns: A new FrameObject instance of the same type as ``page``,
            reflecting the device-under-test's new state after the navigation
            completed.
        """

        if target not in self.G:
            raise ValueError("'%s' isn't in the keyboard" % (target,))

        assert page, "%s page isn't visible" % type(page).__name__
        deadline = time.time() + self.navigate_timeout
        current = _selection_to_text(page.selection)
        while current != target:
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G, current, target))
            log.info("Keyboard: navigating from %s to %s by pressing %r",
                     current, target, keys)
            if not verify_every_keypress:
                for k, _ in keys[:-1]:
                    stbt.press(k)
                keys = keys[-1:]  # only verify the last one
            for key, possible_targets in keys:
                assert stbt.press_and_wait(key, mask=self.mask, stable_secs=0.5)
                page = page.refresh()
                assert page, "%s page isn't visible" % type(page).__name__
                current = _selection_to_text(page.selection)
                assert current in possible_targets, \
                    "Expected to see %s after pressing %s, but saw %r" % (
                        _join_with_commas(
                            [repr(x) for x in sorted(possible_targets)],
                            last_one=" or "),
                        key,
                        current)
        return page

    @staticmethod
    def parse_edgelist(graph):
        """Create a `networkx.DiGraph` from a string specification of the graph.

        This is useful when you want to specify part of the keyboard's
        navigation graph programmatically using `stbt.grid_to_navigation_graph`
        (for the parts of the keyboard that are laid out in a grid and behave
        regularly) but you still need to specify some extra edges that behave
        differently. For example::

            letters = stbt.Grid(...)
            space_bar = stbt.Keyboard.parse_edgelist('''
                C SPACE KEY_DOWN
                V SPACE KEY_DOWN
                B SPACE KEY_DOWN
                SPACE C KEY_UP
                SPACE V KEY_UP
                SPACE B KEY_UP
            ''')
            keyboard = stbt.Keyboard(networkx.compose_all([
                stbt.grid_to_navigation_graph(letters),
                space_bar]))

        :param str graph: See the `Keyboard` constructor.
        :returns: A new `networkx.DiGraph` instance.
        """
        return nx.parse_edgelist(graph.split("\n"),
                                 create_using=nx.DiGraph(),
                                 data=[("key", text_type)])


def _selection_to_text(selection):
    if hasattr(selection, "text"):
        return selection.text
    else:
        return selection


def _keys_to_press(G, source, target):
    path = nx.shortest_path(G, source=source, target=target, weight="weight")
    # nx.shortest_path(G, "A", "V") -> ["A", "H", "O", "V"]
    # nx.shortest_path(G, "A", "A") -> ["A"]
    if len(path) == 1:
        return
    for s, t in zip(path[:-1], path[1:]):
        key = G[s][t]["key"]
        possible_targets = set(tt for _, tt, kk in G.edges(s, data="key")
                               if kk == key)
        yield key, possible_targets

        # If there are multiple edges from this node with the same key, we
        # don't know which one we will *actually* end up on. So don't do
        # any further blind keypresses; let the caller re-calculate and call
        # us again.
        if len(possible_targets) > 1:
            break


def _add_weights(G):
    for node in G:
        edges = list(G.edges(node, data="key"))
        keys = set(k for _, _, k in edges)
        for key in keys:
            targets = [t for _, t, k in edges if k == key]
            if len(targets) > 1:
                # Nondeterministic: Multiple targets from the same node with
                # the same action (key). No doubt the keyboard-under-test *is*
                # deterministic, but our model of it (in the test-pack) isn't
                # because we don't remember the previous nodes before we
                # landed on the current node. Give these edges a large weight
                # so that the shortest path algorithm doesn't think it can
                # take a shortcut through here.
                for target in targets:
                    G[node][target]["weight"] = 100


def _join_with_commas(items, last_one=", "):
    """
    >>> _join_with_commas(["A", "B", "C"], last_one=" or ")
    'A, B or C'
    >>> _join_with_commas(["A", "C"], last_one=" or ")
    'A or C'
    >>> _join_with_commas(["A"], last_one=" or ")
    'A'
    >>> _join_with_commas([], last_one=" or ")
    ''
    """
    if len(items) > 1:
        return last_one.join([
            ", ".join(items[:-1]),
            items[-1]])
    elif len(items) == 1:
        return items[0]
    else:
        return ""
