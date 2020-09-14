# coding: utf-8
"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import re
import time
from logging import getLogger

import networkx as nx
import numpy
from attr import attrs, attrib
from _stbt.imgutils import load_image
from _stbt.types import Region
from _stbt.utils import basestring, text_type


log = getLogger("stbt.keyboard")


@attrs(frozen=True)
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

    def __init__(self, graph=None, mask=None, navigate_timeout=20):
        if graph is not None:
            raise ValueError(
                "The `graph` parameter of `stbt.Keyboard` constructor is "
                "deprecated. See the API documentation for details.")
        self.G = nx.DiGraph()
        self.G_ = None  # navigation without shift transitions that type text
        self.modes = set()

        self.mask = None
        if isinstance(mask, numpy.ndarray):
            self.mask = mask
        elif mask:
            self.mask = load_image(mask)

        self.navigate_timeout = navigate_timeout

        self._any_with_region = False
        self._any_without_region = False
        self._any_with_mode = False
        self._any_without_mode = False

    def add_key(self, name, text=None, region=None, mode=None):
        """Add a key to the model (specification) of the keyboard.

        :param str name: The text or label you can see on the key.

        :param str text: The text that will be typed if you press OK on the
            key. If not specified, defaults to ``name`` if ``name`` is exactly
            1 character long, otherwise it defaults to ``""`` (an empty
            string). An empty string indicates that the key doesn't type any
            text when pressed (for example a "caps lock" key to change modes).

        :param Region region: The location of this key on the screen. If
            specified, you can look up a key's name & text by region using
            `Keyboard.find_key`.

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

        :raises: `ValueError` if the key is already present in the model.
        """
        return self._add_key({"name": name, "text": text, "region": region,
                              "mode": mode})

    def find_key(self, name=None, text=None, region=None, mode=None):
        """Find a key in the model (specification) of the keyboard.

        Specify one or more of ``name``, ``text``, ``region``, and ``mode``
        (as many as are needed to uniquely identify the key).

        For example, your Page Object's ``selection`` property would do some
        image processing to find the selection on screen, and then use
        ``find_key`` to identify the current key based on the location of that
        selection::

            class LoginPage(stbt.FrameObject):

                kb = stbt.Keyboard(...)

                @property
                def selection(self):
                    m = stbt.match("selection.png", frame=self._frame)
                    if m:
                        return self.kb.find_key(region=m.region)

        :returns: An object that unambiguously identifies the key in the
            model.

        :raises: `ValueError` if the key does not exist in the model, or if it
            can't be identified unambiguously (that is, if two or more keys
            match the given parameters).
        """
        return self._find_key({"name": name, "text": text, "region": region,
                               "mode": mode})

    def find_keys(self, name=None, text=None, region=None, mode=None):
        """Find matching keys in the model of the keyboard.

        This is like `Keyboard.find_key`, but it returns a list containing any
        keys that match the given parameters. For example, if there is a space
        key in both the lowercase and uppercase modes of the keyboard, calling
        ``find_keys(text=" ")`` will return a list of 2 objects
        ``[Key(text=" ", mode="lowercase"), Key(text=" ", mode="uppercase")]``.

        This method doesn't raise an exception; the list will be empty if no
        keys matched.
        """
        return self._find_keys({"name": name, "text": text, "region": region,
                                "mode": mode})

    def _find_key(self, query, mode=None):
        """Like the public ``find_keys``, but takes a "query"  which can be
        a dict containing one or more of "name", "text", "region", and "mode";
        or a string, which means ``{"name": query}``; or a `Key`.
        """
        keys = self._find_keys(query, mode)
        if len(keys) == 0:
            log.debug("All keys: %r", self.G.nodes())
            raise ValueError("Query %r doesn't match any key in the keyboard"
                             % (_minimal_query(query),))
        elif len(keys) == 1:
            return keys[0]
        else:
            raise ValueError("Ambiguous query %r: Could mean %s" % (
                _minimal_query(query),
                _join_with_commas([str(x) for x in sorted(keys)],
                                  last_one=" or ")))

    def _find_keys(self, query, mode=None):
        """Like the public `find_keys`, but takes a "query" (see _find_key)."""
        if isinstance(query, Key):
            if mode is not None and query.mode != mode:
                raise ValueError("mode %r doesn't match %r" % (mode, query))
            if query in self.G:
                return [query]
            else:
                raise ValueError("%r isn't in the keyboard" % (query,))
        elif isinstance(query, basestring):
            query = {"name": query}
        else:
            query = _minimal_query(query)
        if mode is not None and "mode" in query and query["mode"] != mode:
            raise ValueError("mode %r doesn't match key %r" % (mode, query))
        if len(query) == 0:
            raise ValueError("Empty query %r" % (query,))
        if mode is not None:
            query["mode"] = mode
        return [x for x in self.G.nodes()
                if all(Keyboard.QUERYER[k](x, v) for k, v in query.items())]

    QUERYER = {
        "name": lambda x, v: x.name == v,
        "text": lambda x, v: x.text == v,
        "region": lambda x, v: (x.region is not None and
                                x.region.contains(v.center)),
        "mode": lambda x, v: x.mode == v,
    }

    def _find_or_add_key(self, query):
        """Note: We don't want to expose this operation in the public API
        because it's too easy to create bugs in your model of the keyboard.
        That's why `add_transition` requires you to add the keys explicitly,
        first.
        """
        keys = self._find_keys(query)
        if len(keys) == 0:
            return self._add_key(query)
        elif len(keys) == 1:
            return keys[0]
        else:
            raise ValueError("Ambiguous key %r: Could mean %s" % (
                _minimal_query(query),
                _join_with_commas([str(x) for x in sorted(keys)],
                                  last_one=" or ")))

    def _add_key(self, spec):
        """Add a node to the graph. Raises if the node already exists."""
        nodes = self._find_keys(spec)
        if len(nodes) > 0:
            raise ValueError("Key already exists: %r" % (nodes[0],))

        if spec.get("text") is None and len(spec["name"]) == 1:
            spec["text"] = spec["name"]
        node = Key(**spec)
        if node.region is None and self._any_with_region:
            raise ValueError("Key %r doesn't specify 'region', but all the "
                             "other keys in the keyboard do" % (spec,))
        if node.region is not None and self._any_without_region:
            raise ValueError("Key %r specifies 'region', but none of the "
                             "other keys in the keyboard do" % (spec,))
        if node.mode is None and self._any_with_mode:
            raise ValueError("Key %r doesn't specify 'mode', but all the "
                             "other keys in the keyboard do" % (spec,))
        if node.mode is not None and self._any_without_mode:
            raise ValueError("Key %r specifies 'mode', but none of the "
                             "other keys in the keyboard do" % (spec,))
        self.G.add_node(node)
        self.G_ = None
        if node.region is None:  # pylint:disable=simplifiable-if-statement
            self._any_without_region = True
        else:
            self._any_with_region = True
        if node.mode is None:
            self._any_without_mode = True
        else:
            self.modes.add(node.mode)
            self._any_with_mode = True
        return node

    def add_transition(self, source, target, keypress, mode=None,
                       symmetrical=True):
        """Add a transition to the model (specification) of the keyboard.

        For example: To go from "A" to "B", press "KEY_RIGHT" on the remote
        control.

        :param source: The starting key. This can be an object returned from
            `Keyboard.add_key`; or it can be a dict that contains one or more
            of "name", "text", "region", and "mode" (as many as are needed to
            uniquely identify the key using `Keyboard.find_key`). For
            convenience, a single string is treated as "name" (but this may not
            be enough to uniquely identify the key if your keyboard has
            multiple modes).

        :param target: The key you'll land on after pressing the button
            on the remote control. This accepts the same types as ``source``.

        :param str keypress: The name of the key you need to press on the
            remote control, for example "KEY_RIGHT".

        :param str mode: Optional keyboard mode that applies to both ``source``
            and ``target``. For example, the two following calls are the same::

                add_transition("c", " ", "KEY_DOWN", "lowercase")
                add_transition({"name": "c", "mode": "lowercase"},
                               {"name": " ", "mode": "lowercase"},
                               "KEY_DOWN")

        :param bool symmetrical: By default, if the keypress is "KEY_LEFT",
            "KEY_RIGHT", "KEY_UP", or "KEY_DOWN", this will automatically add
            the opposite transition. For example, if you call
            ``add_transition("a", "b", "KEY_RIGHT")`` this will also add the
            transition ``("b", "a", "KEY_LEFT)"``. Set this parameter to False
            to disable this behaviour. This parameter has no effect if
            ``keypress`` is not one of the 4 directional keys.

        :raises: `ValueError` if the ``source`` or ``target`` keys do not exist
            in the model, or if they can't be identified unambiguously.
        """
        source = self._find_key(source, mode)
        target = self._find_key(target, mode)
        self._add_edge(source, target, keypress)
        if symmetrical and keypress in SYMMETRICAL_KEYS:
            self._add_edge(target, source, SYMMETRICAL_KEYS[keypress])

    def _add_edge(self, source, target, key):
        # type: (Key, Key, str) -> None
        self.G.add_edge(source, target, key=key)
        _add_weight(self.G, source, key)
        self.G_ = None

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
                source = self._find_or_add_key({"name": source, "mode": mode})
                target = self._find_or_add_key({"name": target, "mode": mode})
                self.add_transition(source, target, keypress,
                                    symmetrical=symmetrical)
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

        # First add the keys. It's an exception if any of them already exist.
        # The data is a string or a dict; we don't support previously-created
        # Key instances (for now) because what should we do with the existing
        # Key's `region`?
        keys = []
        for cell in grid:
            x, y = cell.position
            if cell.data is None:
                raise ValueError("Grid cell [%i,%i] doesn't have any data"
                                 % (x, y))
            if isinstance(cell.data, basestring):
                spec = {"name": cell.data}
            elif isinstance(cell.data, dict):
                if "mode" in cell.data:
                    if cell.data["mode"] != mode:
                        raise ValueError("Grid cell [%i,%i] specifies mode %r "
                                         "but add_grid specifies mode %r"
                                         % (x, y, cell.data["mode"], mode))
                spec = cell.data.copy()
            else:
                raise ValueError("Unexpected data type %s in grid cell "
                                 "[%i, %i]. Expected str or dict."
                                 % (type(cell.data), x, y))

            spec["mode"] = mode
            spec["region"] = cell.region
            keys.append(self._add_key(spec))

        # Now add the transitions. Note that `add_transition` defaults to
        # `symmetrical=True`, which will add the down & right transitions.
        for cell in grid:
            x, y = cell.position
            source = keys[grid[x, y].index]
            if x > 0:
                target = keys[grid[x - 1, y].index]
                self.add_transition(source, target, "KEY_LEFT")
            if y > 0:
                target = keys[grid[x, y - 1].index]
                self.add_transition(source, target, "KEY_UP")

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
            if not self._find_keys({"text": letter}):
                raise ValueError("'%s' isn't in the keyboard" % (letter,))

        for letter in text:
            page = self.navigate_to({"text": letter},
                                    page, verify_every_keypress)
            stbt.press_and_wait("KEY_OK", mask=self.mask, stable_secs=0.5,  # pylint:disable=stbt-unused-return-value
                                timeout_secs=1)
            page = page.refresh()
            log.debug("Keyboard: Entered %r; the selection is now on %r",
                      letter, page.selection)
        log.info("Keyboard: Entered %r", text)
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

        targets = self._find_keys(target)
        if not targets:
            raise ValueError("'%s' isn't in the keyboard" % (target,))

        if self.G_ is None:
            # Re-calculate graph without any shift transitions that type text
            self.G_ = _strip_shift_transitions(self.G)

        assert page, "%s page isn't visible" % type(page).__name__
        deadline = time.time() + self.navigate_timeout
        current = page.selection
        while current not in targets:
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G_, current, targets))
            log.debug("Keyboard: navigating from %r to %r by pressing %r",
                      current, target, [k for k, _ in keys])
            if not verify_every_keypress:
                for k, _ in keys[:-1]:
                    stbt.press(k)
                keys = keys[-1:]  # only verify the last one
            for key, possible_targets in keys:
                assert stbt.press_and_wait(key, mask=self.mask, stable_secs=0.5)
                page = page.refresh()
                assert page, "%s page isn't visible" % type(page).__name__
                current = page.selection
                assert current in possible_targets, \
                    "Expected to see %s after pressing %s, but saw %r" % (
                        _join_with_commas(
                            [repr(x) for x in sorted(possible_targets)],
                            last_one=" or "),
                        key,
                        current)
        return page


def _minimal_query(query):
    if not isinstance(query, dict):
        return query
    return {k: v for k, v in query.items() if v is not None}


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


def _strip_shift_transitions(G):
    G_ = nx.DiGraph()
    for node in G.nodes():
        G_.add_node(node)
    for u, v, data in G.edges(data=True):
        if data["key"] == "KEY_OK" and u.text:
            continue
        G_.add_edge(u, v, **data)
    return G_


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
