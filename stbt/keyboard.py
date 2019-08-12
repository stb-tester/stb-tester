# coding: utf-8
"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import time
from logging import getLogger

import networkx as nx
import numpy
import stbt


log = getLogger("stbt.keyboard")


class Keyboard(object):
    """Helper for navigating an on-screen keyboard using the remote control.

    You customize for the appearance & behaviour of the keyboard you're testing
    by specifying two things:

    * A `stbt.FrameObject` class that can tell you which key is currently
      selected on the screen. See the ``page`` parameter to ``enter_text`` and
      ``navigate_to``, below.

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

            Q W KEY_RIGHT
            Q A KEY_DOWN
            W Q KEY_LEFT
            <etc>

        For nodes that enter a character, use that character as the node name.
        For the space-bar use SPACE. For other nodes that don't enter a
        character when pressed use a descriptive name such as CLEAR or ENTER
        (these nodes won't be used by ``enter_text`` but you can use them as a
        target of ``navigate_to``).

        For advanced users: instead of a string, ``graph`` can be a
        `networkx.DiGraph` where each edge has an attribute called ``key`` with
        a value like ``"KEY_RIGHT"`` etc.

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

    .. _Directed Graph: https://en.wikipedia.org/wiki/Directed_graph
    """

    def __init__(self, graph, mask=None, navigate_timeout=20):
        if isinstance(graph, nx.DiGraph):
            self.G = graph
        else:
            self.G = nx.parse_edgelist(graph.split("\n"),
                                       create_using=nx.DiGraph(),
                                       data=[("key", str)])
        nx.relabel_nodes(self.G, {"SPACE": " "}, copy=False)
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

    def enter_text(self, page, text):
        """
        Enter the specified text using the on-screen keyboard.

        :param stbt.FrameObject page: An instance of a `stbt.FrameObject`
            sub-class that describes the appearance of the on-screen keyboard.
            It must implement the following:

            * ``selection`` — property that returns the name of the currently
              selected character, for example "A" or " ". This property can
              return a string, or an object with a ``text`` attribute that is
              a string.

            The ``page`` instance that you provide must represent the current
            state of the device-under-test.

        :param str text: The text to enter. If your keyboard only supports a
            single case then you need to convert the text to uppercase or
            lowercase, as appropriate, before passing it to this method.

        Typically your FrameObject will provide its own ``enter_text`` method,
        so your test scripts won't call this ``Keyboard`` class directly. For
        example::

            class YouTubeSearch(stbt.FrameObject):
                _kb = stbt.Keyboard('''
                    A B KEY_RIGHT
                    ...etc...
                    ''')

                @property
                def is_visible(self):
                    ...  # implementation not shown

                @property
                def selection(self):
                    ...  # implementation not shown

                def enter_text(self, text):
                    self._kb.enter_text(page=self, text=text.upper())
                    self._kb.navigate_to(page=self, target="SEARCH")
                    stbt.press("KEY_OK")
        """

        for letter in text:
            if letter not in self.G:
                raise ValueError("'%s' isn't in the keyboard" % (letter,))

        for letter in text:
            page = self.navigate_to(page, letter)
            stbt.press("KEY_OK")
        return page

    def navigate_to(self, page, target):
        """Move the selection to the specified character.

        Note that this won't press KEY_OK on the target, it only moves the
        selection there.

        :param stbt.FrameObject page: See ``enter_text``.
        :param str target: The key or button to navigate to, for example "A",
            " ", or "CLEAR".

        :returns: A new FrameObject instance of the same type as ``page``,
            reflecting the device-under-test's new state after the navigation
            completed.
        """

        if target not in self.G:
            raise ValueError("'%s' isn't in the keyboard" % (target,))

        deadline = time.time() + self.navigate_timeout
        current = _selection_to_text(page.selection)
        while current != target:
            assert page, "%s page isn't visible" % type(page).__name__
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G, current, target))
            log.info("Navigating from %s to %s by pressing %s",
                     current, target, ", ".join(keys))
            for k in keys[:-1]:
                stbt.press(k)
            assert stbt.press_and_wait(keys[-1], mask=self.mask)
            page = page.refresh()
            current = _selection_to_text(page.selection)
        return page


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
        yield key

        # If there are multiple edges from this node with the same key, we
        # don't know which one we will *actually* end up on. So don't do
        # any further blind keypresses; let the caller re-calculate and call
        # us again.
        if len([tt for _, tt, kk in G.edges(s, data="key") if kk == key]) > 1:
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
