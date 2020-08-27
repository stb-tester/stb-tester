# coding: utf-8
"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import re
import time
from collections import namedtuple
from logging import getLogger

import networkx as nx
import numpy
from attr import attrs, attrib
from _stbt.imgutils import load_image
from _stbt.types import Region
from _stbt.utils import basestring, py3, text_type


log = getLogger("stbt.keyboard")


@attrs(**{"frozen": True, "kw_only": True} if py3 else {"frozen": True})
class Key(object):
    """A node in the directed graph, representing a key on the keyboard.

    This is an immutable object so that it is hashable (it must be hashable
    so that we can use it as a node of networkx graphs).

    The user can specify any of the attributes (but at least ``name``). See
    `Keyboard.add_key`.

    This is an implementation detail, not part of the public API. But we do
    return these as opaque objects from `Keyboard.add_key`.
    """
    name = attrib(default=None, type=text_type)
    text = attrib(default=None, type=text_type)
    region = attrib(default=None, type=Region)
    mode = attrib(default=None, type=text_type)


SYMMETRICAL_KEYS = {
    "KEY_DOWN": "KEY_UP",
    "KEY_UP": "KEY_DOWN",
    "KEY_LEFT": "KEY_RIGHT",
    "KEY_RIGHT": "KEY_LEFT",
}


class Keyboard(object):
    """Models the behaviour of an on-screen keyboard.

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

    :param graph: Deprecated. First create the Keyboard object, then use
    `add_key`, `add_transition`, `add_transitions_from_edgelist`, and
    `add_grid` to build the model of the keyboard.

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

    def __init__(self, graph=None, mask=None, navigate_timeout=20):
        if graph is not None:
            raise ValueError(
                "The `graph` parameter of `stbt.Keyboard` constructor is "
                "deprecated. See the API documentation for details.")
        self.G = nx.DiGraph()

        self.mask = None
        if isinstance(mask, numpy.ndarray):
            self.mask = mask
        elif mask:
            self.mask = load_image(mask)

        self.navigate_timeout = navigate_timeout

    def add_key(self, name, text=None, region=None, mode=None):
        """Add a key to the model (specification) of the keyboard.

        If the key already exists, just return it.

        :param str name: The text or label you can see on the key.

        :param str text: The text that will be typed if you press OK on the
            key. If not specified, defaults to ``name`` if ``name`` is exactly
            1 character long, otherwise it defaults to ``""`` (an empty
            string). An empty string indicates that the key doesn't type any
            text when pressed (for example a "caps lock" key to change modes).

        :param Region region: The location of this key on the screen. If
            specified, you can look up key names & text by region.

        :param str mode: The mode that the key belongs to, such as "lowercase",
            "uppercase", "shift", or "symbols", if your keyboard supports
            different modes. Note that the same key, if visible in different
            modes, needs to be specified as separate keys (for example
            ``(name="space", mode="lowercase")`` and ``(name="space",
            mode="uppercase")`` because their navigation connections are
            totally different: pressing up from the former goes to lowercase
            "c", or to uppercase "C" from the latter. ``mode`` is optional if
            your keyboard doesn't have modes, or if you only need to use the
            default mode.

        :returns: The added key. This is an object that you can use with
            `Keyboard.add_transition`.
        """
        return self._add_node({"name": name, "text": text, "region": region,
                               "mode": mode})

    def add_transition(self, source, target, keypress, symmetrical=True):
        """Add a transition to the model (specification) of the keyboard.

        For example: To go from "A" to "B", press "KEY_RIGHT" on the remote
        control.

        :param source: The starting key. This can be an object returned from
            `Keyboard.add_key`, or it can be a dict that contains one or more
            of "name", "text", "region", and "mode" (as many as are needed to
            uniquely identify the key). For example: ``{"name": "a"}``.
            For convenience, a single string is treated as "name" (but this may
            not be enough to uniquely identify the key if your keyboard has
            multiple modes).

        :param target: The key you'll land on after pressing the button
            on the remote control. This accepts the same types as ``source``.

        :param str keypress: The name of the key you need to press on the
            remote control, for example "KEY_RIGHT".

        :param bool symmetrical: By default, if the keypress is "KEY_LEFT",
            "KEY_RIGHT", "KEY_UP", or "KEY_DOWN", this will automatically add
            the opposite transition. For example, if you call
            ``add_transition("a", "b", "KEY_RIGHT")`` this will also add the
            transition ``("b", "a", "KEY_LEFT)"``. Set this parameter to False
            to disable this behaviour. This parameter has no effect if
            ``keypress`` is not one of the 4 directional keys.
        """
        source = self._add_node(source)
        target = self._add_node(target)
        self._add_edge(source, target, keypress)
        if symmetrical and keypress in SYMMETRICAL_KEYS:
            self._add_edge(target, source, SYMMETRICAL_KEYS[keypress])

    def add_transitions_from_edgelist(self, edgelist, mode=None,
                                      symmetrical=True):
        """Add keys and transitions specified in a string in "edgelist" format.

        :param str edgelist: A multi-line string where each line is in the
            format ``<source_name> <target_name> <keypress>``. For example, the
            specification for a qwerty keyboard might look like this::

                '''
                Q W KEY_RIGHT
                Q A KEY_DOWN
                W E KEY_RIGHT
                ...
                '''

            The name "SPACE" will be converted to the space character (" ").
            This is because space is used as the field separator; otherwise it
            wouldn't be possible to specify the space key using this format.

        :param str mode: The mode that applies to all the keys specified in
            ``edgelist``. See `Keyboard.add_key` for more details about modes.
            It isn't possible to specify transitions *between* different modes
            using this edgelist format; use `Keyboard.add_transition` for that.

        :param bool symmetrical: See `Keyboard.add_transition`.
        """
        for i, line in enumerate(edgelist.split("\n")):
            if re.match(r"^\s*###", line):  # comment
                continue
            fields = line.split()
            if len(fields) == 0:
                continue
            elif len(fields) == 3:
                source, target, keypress = fields
                if source == "SPACE":
                    source = " "
                if target == "SPACE":
                    target = " "
                self.add_transition({"name": source, "mode": mode},
                                    {"name": target, "mode": mode},
                                    keypress,
                                    symmetrical)
            else:
                raise ValueError(
                    "Invalid line %d in keyboard edgelist "
                    "(must contain 3 fields): %r"
                    % (i, line.strip()))

    def add_grid(self, grid, mode=None):
        """Add keys, and transitions between them, to the model of the keyboard.

        If the keyboard (or part of the keyboard) is arranged in a regular
        grid, you can use `stbt.Grid` to easily specify the positions of those
        keys. This only works if the columns & rows are all of the same size.

        For example::

            kb = stbt.Keyboard()
            kb.add_grid(stbt.Grid(region, data=["ABCDEFG",
                                                "HIJKLMN",
                                                "OPQRSTU",
                                                "VWXYZ-'"])

        :param stbt.Grid grid: The grid to model. The data associated with each
            cells will be used for the key's "name" attribute (see
            `Keyboard.add_key`).

        :param str mode: The mode that applies to all the keys specified in
            ``grid``. See `Keyboard.add_key` for more details about modes.
        """

        for cell in grid:
            x, y = cell.position
            if cell.data is None:
                # `add_edge` would raise too, but this is a clearer message.
                raise ValueError("Grid cell [%i,%i] doesn't have any data"
                                 % (x, y))
            source = Key(name=cell.data, region=cell.region, mode=mode)
            if x > 0:
                target = grid[x - 1, y]
                self.add_transition(
                    source,
                    Key(name=target.data, region=target.region, mode=mode),
                    "KEY_LEFT")
            if y > 0:
                target = grid[x, y - 1]
                self.add_transition(
                    source,
                    Key(name=target.data, region=target.region, mode=mode),
                    "KEY_UP")
            # Note: add_transition's symmetrical=True will add the down &
            # right transitions.

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

        import stbt_core as stbt

        for letter in text:
            # Sanity check so we don't fail halfway through typing.
            if not self._find_nodes({"text": letter}):
                raise ValueError("'%s' isn't in the keyboard" % (letter,))

        prev = None
        for letter in text:
            page = self.navigate_to({"text": letter},
                                    page, verify_every_keypress)
            if letter == prev:
                stbt.press("KEY_OK", interpress_delay_secs=1)
            else:
                stbt.press("KEY_OK")
            prev = letter
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

        import stbt_core as stbt

        targets = self._find_nodes(target)
        if not targets:
            raise ValueError("'%s' isn't in the keyboard" % (target,))

        assert page, "%s page isn't visible" % type(page).__name__
        deadline = time.time() + self.navigate_timeout
        current = self._page_to_node(page)
        while current not in targets:
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G, current, targets))
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
                current = self._page_to_node(page)
                assert current in possible_targets, \
                    "Expected to see %s after pressing %s, but saw %r" % (
                        _join_with_commas(
                            [repr(x) for x in sorted(possible_targets)],
                            last_one=" or "),
                        key,
                        current)
        return page

    def _add_node(self, spec):
        """Add a node to the graph. No-op if the node already exists. Raises
        if spec matches more than 1 existing node.
        """
        if isinstance(spec, Key):
            spec = Key.__dict__
        elif isinstance(spec, basestring):
            spec = {"name": spec}
        nodes = self._find_nodes(spec)
        if len(nodes) == 0:
            if spec.get("text") is None and len(spec["name"]) == 1:
                spec["text"] = spec["name"]
            node = Key(**spec)
            self.G.add_node(node)
            return node
        elif len(nodes) == 1:
            return nodes[0]
        else:
            raise ValueError("Ambiguous key: Could mean " +
                             _join_with_commas([str(x) for x in sorted(nodes)],
                                               last_one=" or "))

    def _find_nodes(self, spec):
        if isinstance(spec, Key):
            spec = Key.__dict__
        elif isinstance(spec, basestring):
            spec = {"name": spec}
        spec = {k: v
                for k, v in spec.items()
                if v is not None}
        return [x for x in self.G.nodes() if all(getattr(x, k, None) == v
                                                 for k, v in spec.items())]

    def _add_edge(self, source, target, key):
        # type: (Key, Key, str) -> None
        self.G.add_edge(source, target, key=key)
        _add_weight(self.G, source, key)

    def _page_to_node(self, page):
        selection = getattr(page, "selection")
        mode = getattr(page, "mode")
        name = None
        region = None
        if isinstance(selection, basestring):
            name = selection
        else:
            if hasattr(selection, "text"):
                name = selection.text
            if hasattr(selection, "region"):
                region = selection.region
            if mode is None and hasattr(selection, "mode"):
                mode = selection.mode
        spec = {"name": name, "region": region, "mode": mode}
        nodes = self._find_nodes(spec)
        if len(nodes) == 0:
            raise RuntimeError("No key %r matches page %r" % (
                {k: v for k, v in spec.items() if v is not None},
                page))
        if len(nodes) == 1:
            return nodes[0]
        else:
            raise RuntimeError(
                "Page %r doesn't specify current key unambiguously. "
                "Matching keys for query %r: %r" % (
                    page,
                    {k: v for k, v in spec.items() if v is not None},
                    nodes))


def _keys_to_press(G, source, targets):
    paths = sorted(
        [nx.shortest_path(G, source=source, target=t, weight="weight")
         for t in targets],
        key=len)
    path = paths[0]
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


def _add_weight(G, source, key):
    """Add high weight for non-deterministic edges.

    "Non-deterministic" means multiple targets from the same node with the same
    action (key). No doubt the keyboard-under-test *is* deterministic, but our
    model of it (in the test-pack) isn't, because we don't remember the
    previous nodes before we landed on the current node. Give these edges a
    large weight so that the shortest path algorithm doesn't think it can take
    a shortcut through here.
    """
    targets = [t for _, t, k in G.edges(source, data="key")
               if k == key]
    if len(targets) > 1:
        for t in targets:
            G[source][t]["weight"] = 100


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
