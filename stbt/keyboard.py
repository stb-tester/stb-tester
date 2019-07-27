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
    """Enter text into an on-screen keyboard using the remote control.

    The constructor takes the following parameters:

    :param stbt.FrameObject page: An instance of a `stbt.FrameObject` sub-class
        that implements the following:

        * ``selection`` — property that returns the name of the currently
          selected character, for example "A" or " ".

    :param str graph: A specification of the complete navigation graph (state
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

    """

    def __init__(self, page, graph, mask=None, navigate_timeout=20):
        self.page = page
        self.G = nx.parse_edgelist(graph.split("\n"),
                                   create_using=nx.DiGraph,
                                   data=[("key", str)])
        nx.relabel_nodes(self.G, {"SPACE": " "}, copy=False)

        self.mask = None
        if isinstance(mask, numpy.ndarray):
            self.mask = mask
        elif mask:
            self.mask = stbt.load_image(mask)

        self.navigate_timeout = navigate_timeout

    # TODO: self.page.selection.text
    #   This property can return a string, or an object with a ``text``
    #   attribute that is a string.
    # TODO: case sensitive

    def enter_text(self, text):
        if not text:
            return  # finished
        letter = text[0]
        self.navigate_to(letter)
        stbt.press("KEY_OK")
        self.enter_text(text[1:])

    def navigate_to(self, target):
        deadline = time.time() + self.navigate_timeout
        current = self.page.selection
        while current != target:
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G, current, target))
            log.info("Keyboard: navigating from %s to %s by pressing %r",
                     current, target, keys)
            for k in keys[:-1]:
                stbt.press(k)
            assert stbt.press_and_wait(keys[-1], mask=self.mask)
            self.page = self.page.refresh()
            current = self.page.selection


def _keys_to_press(G, source, target):
    path = nx.shortest_path(G, source=source, target=target)
    # nx.shortest_path(G, "A", "V") -> ["A", "H", "O", "V"]
    # nx.shortest_path(G, "A", "A") -> ["A"]
    if len(path) == 1:
        return
    for s, t in zip(path[:-1], path[1:]):
        key = G.edges[s, t]["key"]
        yield key

        # If there are multiple edges from this node with the same key, we
        # don't know which one we will *actually* end up on. So don't do
        # any further blind keypresses; let the caller re-calculate and call
        # us again.
        if len([tt for _, tt, kk in G.edges(s, data="key") if kk == key]) > 1:
            break
