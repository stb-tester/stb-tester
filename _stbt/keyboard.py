"""Copyright 2019-2020 Stb-tester.com Ltd."""

from __future__ import annotations

import dataclasses
import re
import time
import typing
from collections import defaultdict
from logging import getLogger
from typing import Optional, TypeAlias, TypeVar

from attr import attrs, attrib
from _stbt.frameobject import FrameObject
from _stbt.grid import Grid
from _stbt.imgutils import FrameT
from _stbt.mask import MaskTypes, load_mask
from _stbt.transition import Transition, TransitionStatus
from _stbt.types import KeyT, Region


FrameObjectT = TypeVar("FrameObjectT", bound=FrameObject)
QueryT: TypeAlias = "Keyboard.Key | dict[str, str] | str"

log = getLogger("stbt.Keyboard")


class Keyboard():
    '''Models the behaviour of an on-screen keyboard.

    You customize for the appearance & behaviour of the keyboard you're testing
    by specifying two things:

    * A `Directed Graph`_ that specifies the navigation between every key on
      the keyboard. For example: When *A* is focused, pressing *KEY_RIGHT* on
      the remote control goes to *B*, and so on.

    * A `Page Object`_ that tells you which key is currently focused on the
      screen. See the ``page`` parameter to `enter_text` and `navigate_to`.

    The constructor takes the following parameters:

    :param str|numpy.ndarray|Mask|Region mask:
        A mask to use when calling `stbt.press_and_wait` to determine when the
        current focus has finished moving. If the search page has a
        blinking cursor you need to mask out the region where the cursor can
        appear, as well as any other regions with dynamic content (such as a
        picture-in-picture with live TV). See `stbt.press_and_wait` for more
        details about the mask.

    :type navigate_timeout: int or float
    :param navigate_timeout: Timeout (in seconds) for ``navigate_to``. In
        practice ``navigate_to`` should only time out if you have a bug in your
        model or in the real keyboard under test.

    .. _keyboard-example:

    For example, let's model the lowercase keyboard from the YouTube search
    page on Apple TV:

    .. figure:: images/keyboard/youtube-keyboard.png
       :align: center

    ::

        # 1. Specify the keyboard's navigation model
        # ------------------------------------------

        kb = stbt.Keyboard()

        # The 6x6 grid of letters & numbers:
        kb.add_grid(stbt.Grid(stbt.Region(x=125, y=175, right=425, bottom=475),
                              data=["abcdef",
                                    "ghijkl",
                                    "mnopqr",
                                    "stuvwx",
                                    "yz1234",
                                    "567890"]))
        # The 3x1 grid of special keys:
        kb.add_grid(stbt.Grid(stbt.Region(x=125, y=480, right=425, bottom=520),
                              data=[[" ", "DELETE", "CLEAR"]]))

        # The `add_grid` calls (above) defined the transitions within each grid.
        # Now we need to specify the transitions from the bottom row of numbers
        # to the larger keys below them:
        #
        #     5 6 7 8 9 0
        #     ↕ ↕ ↕ ↕ ↕ ↕
        #     SPC DEL CLR
        #
        # Note that `add_transition` adds the symmetrical transition (KEY_UP)
        # by default.
        kb.add_transition("5", " ", "KEY_DOWN")
        kb.add_transition("6", " ", "KEY_DOWN")
        kb.add_transition("7", "DELETE", "KEY_DOWN")
        kb.add_transition("8", "DELETE", "KEY_DOWN")
        kb.add_transition("9", "CLEAR", "KEY_DOWN")
        kb.add_transition("0", "CLEAR", "KEY_DOWN")

        # 2. A Page Object that describes the appearance of the keyboard
        # --------------------------------------------------------------

        class SearchKeyboard(stbt.FrameObject):
            """The YouTube search keyboard on Apple TV"""

            @property
            def is_visible(self):
                # Implementation left to the reader. Should return True if the
                # keyboard is visible and focused.
                ...

            @property
            def focus(self):
                """Returns the focused key.

                Used by `Keyboard.enter_text` and `Keyboard.navigate_to`.

                Note: The reference image (focus.png) is carefully cropped
                so that it will match the normal keys as well as the larger
                "SPACE", "DELETE" and "CLEAR" keys. The middle of the image
                (where the key's label appears) is transparent so that it will
                match any key.
                """
                m = stbt.match("focus.png", frame=self._frame)
                if m:
                    return kb.find_key(region=m.region)
                else:
                    return None

            # Your Page Object can also define methods for your test scripts to
            # use:

            def enter_text(self, text):
                return kb.enter_text(text.lower(), page=self)

            def clear(self):
                page = kb.navigate_to("CLEAR", page=self)
                stbt.press_and_wait("KEY_OK")
                return page.refresh()

    For a detailed tutorial, including an example that handles multiple
    keyboard modes (lowercase, uppercase, and symbols) see our article
    `Testing on-screen keyboards <https://stb-tester.com/manual/keyboard>`__.

    Changed in v33:

    * Added class `stbt.Keyboard.Key` (the type returned from `find_key`). This
      used to be a private API, but now it is public so that you can use it in
      type annotations for your Page Object's ``focus`` property.
    * Tries to recover from missed or double keypresses. To disable this
      behaviour specify ``retries=0`` when calling `enter_text` or
      `navigate_to`.
    * Increased default ``navigate_timeout`` from 20 to 60 seconds.

    Changed in v34:

    * The property of the ``page`` object should be called ``focus``, not
      ``selection`` (for backward compatibility we still support ``selection``).

    .. _Page Object: https://stb-tester.com/manual/object-repository#what-is-a-page-object
    .. _Directed Graph: https://en.wikipedia.org/wiki/Directed_graph
    '''

    @attrs(frozen=True)
    class Key():
        """Represents a key on the on-screen keyboard.

        This is returned by `stbt.Keyboard.find_key`. Don't create instances of
        this class directly.

        It has attributes ``name``, ``text``, ``region``, and ``mode``. See
        `Keyboard.add_key`.
        """
        # This is an immutable object so that it is hashable (it must be
        # hashable so that we can use it as a node of networkx graphs).
        name = attrib(default=None, type=str)
        text = attrib(default=None, type=str)
        region = attrib(default=None, type=Region)
        mode = attrib(default=None, type=str)

    def __init__(
        self, *, mask: MaskTypes = Region.ALL, navigate_timeout: float = 60
    ):
        from networkx import DiGraph

        self.G = DiGraph()
        self.G_ = None  # navigation without shift transitions that type text
        self.modes = set()
        self.name_index = defaultdict(list)

        self.mask = load_mask(mask)
        self.navigate_timeout = navigate_timeout

        self.symmetrical_keys = {
            "KEY_DOWN": "KEY_UP",
            "KEY_UP": "KEY_DOWN",
            "KEY_LEFT": "KEY_RIGHT",
            "KEY_RIGHT": "KEY_LEFT",
        }

        self._any_with_region = False
        self._any_without_region = False
        self._any_with_mode = False
        self._any_without_mode = False

    def add_key(
        self,
        name: str,
        text: Optional[str] = None,
        region: Optional[Region] = None,
        mode: Optional[str] = None,
    ):
        """Add a key to the model (specification) of the keyboard.

        :param str name: The text or label you can see on the key.

        :param str text: The text that will be typed if you press OK on the
            key. If not specified, defaults to ``name`` if ``name`` is exactly
            1 character long, otherwise it defaults to ``""`` (an empty
            string). An empty string indicates that the key doesn't type any
            text when pressed (for example a "caps lock" key to change modes).

        :param stbt.Region region: The location of this key on the screen. If
            specified, you can look up a key's name & text by region using
            ``find_key(region=...)``.

        :param str mode: The mode that the key belongs to (such as "lowercase",
            "uppercase", "shift", or "symbols") if your keyboard supports
            different modes. Note that the same key, if visible in different
            modes, needs to be modelled as separate keys (for example
            ``(name=" ", mode="lowercase")`` and
            ``(name=" ", mode="uppercase")``) because their navigation
            connections are totally different: pressing up from the former goes
            to lowercase "c", but pressing up from the latter goes to uppercase
            "C". ``mode`` is optional if your keyboard doesn't have modes, or
            if you only need to use the default mode.

        :returns: The added key (`stbt.Keyboard.Key`). This is an object that
            you can use with `add_transition`.

        :raises: `ValueError` if the key is already present in the model.
        """
        return self._add_key({"name": name, "text": text, "region": region,
                              "mode": mode})

    def find_key(
        self,
        name: Optional[str] = None,
        text: Optional[str] = None,
        region: Optional[Region] = None,
        mode: Optional[str] = None,
    ) -> Key:
        """Find a key in the model (specification) of the keyboard.

        Specify one or more of ``name``, ``text``, ``region``, and ``mode``
        (as many as are needed to uniquely identify the key).

        For example, your Page Object's ``focus`` property would do some
        image processing to find the position of the focus, and then use
        ``find_key`` to identify the focused key based on that region.

        :returns: A `stbt.Keyboard.Key` object that unambiguously identifies
            the key in the model. It has "name", "text", "region", and "mode"
            attributes. You can use this object as the ``source`` or ``target``
            parameter of `add_transition`.

        :raises: `ValueError` if the key does not exist in the model, or if it
            can't be identified unambiguously (that is, if two or more keys
            match the given parameters).
        """
        return self._find_key({"name": name, "text": text, "region": region,
                               "mode": mode})

    def find_keys(
        self,
        name: Optional[str] = None,
        text: Optional[str] = None,
        region: Optional[Region] = None,
        mode: Optional[str] = None,
    ) -> list[Key]:
        """Find matching keys in the model of the keyboard.

        This is like `find_key`, but it returns a list containing any
        keys that match the given parameters. For example, if there is a space
        key in both the lowercase and uppercase modes of the keyboard, calling
        ``find_keys(text=" ")`` will return a list of 2 objects
        ``[Key(text=" ", mode="lowercase"), Key(text=" ", mode="uppercase")]``.

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

    def _find_keys(self, query, mode=None) -> "list[Key]":
        """Like the public `find_keys`, but takes a "query" (see _find_key)."""
        if isinstance(query, Keyboard.Key):
            if mode is not None and query.mode != mode:
                raise ValueError("mode %r doesn't match %r" % (mode, query))
            if query in self.G:
                return [query]
            else:
                # This shouldn't happen unless you're doing something seriously
                # weird, so let's raise instead of the usual behaviour of
                # returning [].
                raise ValueError("%r isn't in the keyboard" % (query,))
        elif isinstance(query, str):
            query = {"name": query}
        else:
            query = _minimal_query(query)
        if mode is not None and "mode" in query and query["mode"] != mode:
            raise ValueError("mode %r doesn't match key %r" % (mode, query))
        if len(query) == 0:
            raise ValueError("Empty query %r" % (query,))
        if mode is not None:
            query["mode"] = mode
        if "name" in query:
            nodes = self.name_index[query["name"]]
        else:
            nodes = self.G.nodes()
        return [x for x in nodes
                if ("name" not in query or x.name == query["name"]) and
                   ("text" not in query or x.text == query["text"]) and
                   ("region" not in query or (
                    x.region is not None and
                    x.region.contains(query["region"].center))) and
                   ("mode" not in query or x.mode == query["mode"])]

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

    def _add_key(self, spec) -> "Key":
        """Add a node to the graph. Raises if the node already exists."""
        nodes = self._find_keys(spec)
        if len(nodes) > 0:
            raise ValueError("Key already exists: %r" % (nodes[0],))

        if spec.get("text") is None and len(spec["name"]) == 1:
            spec["text"] = spec["name"]
        node = Keyboard.Key(**spec)
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
        self.name_index[node.name].append(node)
        if node.region is None:
            self._any_without_region = True
        else:
            self._any_with_region = True
        if node.mode is None:
            self._any_without_mode = True
        else:
            self.modes.add(node.mode)
            self._any_with_mode = True
        return node

    def add_transition(
        self,
        source: QueryT,
        target: QueryT,
        keypress: KeyT,
        mode: Optional[str] = None,
        symmetrical: bool = True,
    ) -> None:
        """Add a transition to the model (specification) of the keyboard.

        For example: To go from "A" to "B", press "KEY_RIGHT" on the remote
        control.

        :param source: The starting key. This can be a `Key` object returned
            from `add_key` or `find_key`; or it can be a dict that contains one
            or more of "name", "text", "region", and "mode" (as many as are
            needed to uniquely identify the key using `find_key`). For
            convenience, a single string is treated as "name" (but this may not
            be enough to uniquely identify the key if your keyboard has
            multiple modes).

        :param target: The key you'll land on after pressing the button
            on the remote control. This accepts the same types as ``source``.

        :param str keypress: The name of the key you need to press on the
            remote control, for example "KEY_RIGHT".

        :param str mode: Optional keyboard mode that applies to both ``source``
            and ``target``. For example, the two following calls are the same::

                add_transition("c", " ", "KEY_DOWN", mode="lowercase")

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
        if symmetrical and keypress in self.symmetrical_keys:
            self._add_edge(target, source, self.symmetrical_keys[keypress])

    def _add_edge(self, source, target, key):
        # type: (Key, Key, str) -> None
        self.G.add_edge(source, target, key=key)
        _add_weight(self.G, source, key)
        self.G_ = None

    def add_edgelist(
        self,
        edgelist: str,
        mode: Optional[str] = None,
        symmetrical: bool = True,
    ) -> None:
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

            Lines starting with "###" are ignored (comments).

        :param str mode: Optional mode that applies to all the keys specified
            in ``edgelist``. See `add_key` for more details about modes. It
            isn't possible to specify transitions between different modes using
            this edgelist format; use `add_transition` for that.

        :param bool symmetrical: See `add_transition`.
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

    def add_grid(self, grid: Grid, mode: Optional[str] = None,
                 merge: bool = False) -> Grid:
        """Add keys, and transitions between them, to the model of the keyboard.

        If the keyboard (or part of the keyboard) is arranged in a regular
        grid, you can use `stbt.Grid` to easily specify the positions of those
        keys. This only works if the columns & rows are all of the same size.

        If your keyboard has keys outside the grid, you will still need to
        specify the transitions from the edge of the grid onto the outside
        keys, using `add_transition`. See the :ref:`example above
        <keyboard-example>`.

        :param stbt.Grid grid: The grid to model. The data associated with each
            cell will be used for the key's "name" attribute (see
            `add_key`).

        :param str mode: Optional mode that applies to all the keys specified
            in ``grid``. See `add_key` for more details about modes.

        :param bool merge: If True, adjacent keys with the same name and mode
            will be merged, and a single larger key will be added in its place.

        :returns: A new `stbt.Grid` where each cell's data is a key object
            that can be used with `add_transition` (for example to define
            additional transitions from the edges of this grid onto other
            keys).
        """

        # For merging keys allow looking them up by value:
        specs: dict[tuple[tuple[str, typing.Any], ...], list[_MutRegion]] = {}

        # First add the keys. It's an exception if any of them already exist.
        # The data is a string or a dict; we don't support previously-created
        # Key instances because what should we do with the existing Key's
        # `region`?
        for cell in grid:
            x, y = cell.position
            spec: "dict[str, typing.Any]"
            if cell.data is None:
                raise ValueError("Grid cell [%i,%i] doesn't have any data"
                                 % (x, y))
            if isinstance(cell.data, str):
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
            if "region" in spec:
                del spec["region"]

            # Can't use a dict as a key in another dict, so convert to a tuple
            # like ((key, value), ...)
            spec_key = tuple(sorted(spec.items()))
            specs.setdefault(spec_key, []).append(
                _MutRegion(cell.position.x, cell.position.y,
                           cell.position.x + 1, cell.position.y + 1))

        keys: "list[Keyboard.Key | None]" = [None] * (grid.cols * grid.rows)
        for tspec, regions in specs.items():
            if merge:
                regions = _merge_regions(regions)
            for region in regions:
                spec = dict(tspec)
                spec["region"] = Region.bounding_box(
                    grid[region.x, region.y].region,
                    grid[region.right - 1, region.bottom - 1].region)
                key = self._add_key(spec)
                for x in range(region.x, region.right):
                    for y in range(region.y, region.bottom):
                        keys[y * grid.cols + x] = key

        # Now add the transitions.
        for cell in grid:
            x, y = cell.position
            source = keys[grid[x, y].index]
            assert isinstance(source, Keyboard.Key)
            if x > 0:
                target = keys[grid[x - 1, y].index]
                if source is not target:
                    self.add_transition(source, target, "KEY_LEFT",
                                        symmetrical=False)
            if x < grid.cols - 1:
                target = keys[grid[x + 1, y].index]
                if source is not target:
                    self.add_transition(source, target, "KEY_RIGHT",
                                        symmetrical=False)
            if y > 0:
                target = keys[grid[x, y - 1].index]
                if source is not target:
                    self.add_transition(source, target, "KEY_UP",
                                        symmetrical=False)
            if y < grid.rows - 1:
                target = keys[grid[x, y + 1].index]
                if source is not target:
                    self.add_transition(source, target, "KEY_DOWN",
                                        symmetrical=False)

        return Grid(
            region=grid.region,
            data=_reshape_array(keys, cols=grid.cols, rows=grid.rows))

    def enter_text(
        self,
        text: str,
        page: FrameObjectT,
        verify_every_keypress: bool = False,
        retries: int = 2,
    ) -> FrameObjectT:
        """Enter the specified text using the on-screen keyboard.

        :param str text: The text to enter. If your keyboard only supports a
            single case then you need to convert the text to uppercase or
            lowercase, as appropriate, before passing it to this method.

        :param stbt.FrameObject page: An instance of a `stbt.FrameObject`
            sub-class that describes the appearance of the on-screen keyboard.
            It must implement the following:

            * ``focus`` (`Key`) — property that returns a Key object, as
              returned from `find_key`.

            When you call *enter_text*, ``page`` must represent the current
            state of the device-under-test.

        :param bool verify_every_keypress:
            If True, we will read the focused key after every keypress and
            assert that it matches the model. If False (the default) we will
            only verify the focused key corresponding to each of the
            characters in ``text``. For example: to get from *A* to *D* you
            need to press *KEY_RIGHT* three times. The default behaviour will
            only verify that the focused key is *D* after the third keypress.
            This is faster, and closer to the way a human uses the on-screen
            keyboard.

            Set this to True to help debug your model if ``enter_text`` is
            behaving incorrectly.

        :param int retries:
            Number of recovery attempts if a keypress doesn't have the expected
            effect according to the model. Allows recovering from missed
            keypresses and double keypresses.

        :returns: A new FrameObject instance of the same type as ``page``,
            reflecting the device-under-test's new state after the keyboard
            navigation completed.

        Typically your FrameObject will provide its own ``enter_text`` method,
        so your test scripts won't call this ``Keyboard`` class directly. See
        the :ref:`example above <keyboard-example>`.
        """

        log.info("enter_text %r", text)

        for letter in text:
            # Sanity check so we don't fail halfway through typing.
            if not self._find_keys({"text": letter}):
                raise ValueError("'%s' isn't in the keyboard" % (letter,))

        for letter in text:
            page = self.navigate_to({"text": letter},
                                    page, verify_every_keypress, retries)
            self.press_and_wait("KEY_OK", stable_secs=0.5, timeout_secs=1)  # pylint:disable=stbt-unused-return-value
            page = page.refresh()
            property_name, current = self._get_focus(page)
            log.debug("Entered %r; the %s is now on %r",
                      letter, property_name, current)
        log.info("Entered %r", text)
        return page

    def navigate_to(
        self,
        target: QueryT,
        page: FrameObjectT,
        verify_every_keypress: bool = False,
        retries: int = 2,
    ) -> FrameObjectT:
        """Move the focus to the specified key.

        This won't press *KEY_OK* on the target; it only moves the focus there.

        :param target: This can be a Key object returned from `find_key`, or it
            can be a dict that contains one or more of "name", "text",
            "region", and "mode" (as many as are needed to identify the key
            using `find_keys`). If more than one key matches the given
            parameters, ``navigate_to`` will navigate to the closest one. For
            convenience, a single string is treated as "name".
        :param stbt.FrameObject page: See `enter_text`.
        :param bool verify_every_keypress: See `enter_text`.
        :param int retries: See `enter_text`.

        :returns: A new FrameObject instance of the same type as ``page``,
            reflecting the device-under-test's new state after the keyboard
            navigation completed.
        """

        import stbt_core as stbt

        log.info("navigate_to: %r", target)

        targets = self._find_keys(target)
        if not targets:
            raise ValueError("'%s' isn't in the keyboard" % (target,))

        if self.G_ is None:
            # Re-calculate graph without any shift transitions that type text
            self.G_ = _strip_shift_transitions(self.G)

        assert page, "%s page isn't visible" % type(page).__name__
        property_name, current = self._get_focus(page)
        assert current in self.G_, \
            "page.%s (%r) isn't in the keyboard" % (property_name, current)
        deadline = time.time() + self.navigate_timeout
        while current not in targets:
            assert time.time() < deadline, (
                "Keyboard.navigate_to: Didn't reach %r after %s seconds"
                % (target, self.navigate_timeout))
            keys = list(_keys_to_press(self.G_, current, targets))
            log.debug("navigating from %r to %r by pressing %r",
                      current, target, [k for k, _ in keys])
            if not verify_every_keypress:
                for k, _ in keys[:-1]:
                    stbt.press(k)
                keys = keys[-1:]  # only verify the last one
            for key, immediate_targets in keys:
                transition = self.press_and_wait(key, stable_secs=0.5)
                assert transition.status != TransitionStatus.STABLE_TIMEOUT, \
                    "%s didn't stabilise after pressing %s" % (
                        property_name.capitalize(), key,)
                page = page.refresh(frame=transition.frame)
                assert page, "%s page isn't visible" % type(page).__name__
                property_name, current = self._get_focus(page)
                if (current not in immediate_targets and
                        not verify_every_keypress):
                    # Wait a bit longer for focus to reach the target
                    transition = self.wait_for_transition_to_end(
                        initial_frame=page._frame, stable_secs=2)
                    assert transition.status != \
                        TransitionStatus.STABLE_TIMEOUT, \
                        "%s didn't stabilise after pressing %s" % (
                            property_name.capitalize(), key,)
                    page = page.refresh(frame=transition.frame)
                    assert page, "%s page isn't visible" % type(page).__name__
                    property_name, current = self._get_focus(page)
                if current not in immediate_targets:
                    message = (
                        "Expected to see %s after pressing %s, but saw %r."
                        % (_join_with_commas(
                            [repr(x) for x in sorted(immediate_targets)],
                            last_one=" or "),
                           key,
                           current))
                    if retries == 0:
                        assert False, message
                    else:
                        log.debug(message +
                                  (" Retrying %d more times." % (retries,)))
                        retries -= 1
                        break  # to outer loop
        return page

    def press_and_wait(
        self, key: KeyT, timeout_secs: float = 10, stable_secs: float = 1
    ) -> Transition:
        import stbt_core as stbt
        return stbt.press_and_wait(key, mask=self.mask,
                                   timeout_secs=timeout_secs,
                                   stable_secs=stable_secs)

    def wait_for_transition_to_end(
        self,
        initial_frame: Optional[FrameT] = None,
        timeout_secs: float = 10,
        stable_secs: float = 1,
    ):
        import stbt_core as stbt
        return stbt.wait_for_transition_to_end(initial_frame, mask=self.mask,
                                               timeout_secs=timeout_secs,
                                               stable_secs=stable_secs)

    def _get_focus(self, page):
        # `focus` is the official name we support; `selection` for backward
        # compatibility.
        try:
            return "selection", page.selection
        except AttributeError:
            pass
        return "focus", page.focus


@dataclasses.dataclass
class _MutRegion:
    x: int
    y: int
    right: int
    bottom: int


def _merge_regions(posns: list[_MutRegion]):
    """Given a list of regions, merge any that are touching into larger regions.

    This can currently only cope with rectangular regions.
    """
    if len(posns) <= 1:
        # Common case
        return posns
    # First do horizontal merge:
    out: list[_MutRegion] = []
    last = None
    for posn in posns:
        if last and posn.x == last.right and posn.y == last.y:
            last.right += 1
        else:
            last = posn
            out.append(last)

    # Now do vertical merge in >x^2 time because I'm lazy:
    modified = True
    while modified:
        modified = False
        for n, a in enumerate(out):
            for m, b in enumerate(out[n + 1:], n + 1):
                if a.bottom != b.y:
                    continue
                if a.x == b.x and a.right == b.right:
                    a.bottom = b.bottom
                    del out[m]
                    modified = True
                    break
                # Only support rectangles for now:
                if b.x < a.right and a.x < b.right:
                    # Overlapping, but not equal
                    raise NotImplementedError(
                        "Keyboard.add_grid doesn't currently support "
                        "merging non-rectangular regions"
                    )
            if modified:
                break
    return out


def test_merge_regions():
    import textwrap
    import pytest

    def r(s):
        out = []
        s = textwrap.dedent(s)
        for y, line in enumerate(s.split("\n")):
            for x, c in enumerate(line):
                if c == "#":
                    out.append(_MutRegion(x, y, x + 1, y + 1))
        return out

    assert _merge_regions([]) == []
    assert _merge_regions(r("#")) == [_MutRegion(0, 0, 1, 1)]
    assert _merge_regions(r("##")) == [_MutRegion(0, 0, 2, 1)]
    assert _merge_regions(r("#\n#")) == [_MutRegion(0, 0, 1, 2)]
    assert _merge_regions(r(".##\n.##")) == [_MutRegion(1, 0, 3, 2)]
    with pytest.raises(NotImplementedError):
        _merge_regions(r("##\n#."))
    assert _merge_regions(r("""\
        ......##.
        ..##..##.
        ..##....#
        """)) == [_MutRegion(6, 0, 8, 2),
                  _MutRegion(2, 1, 4, 3),
                  _MutRegion(8, 2, 9, 3)]


def _minimal_query(query):
    if not isinstance(query, dict):
        return query
    return {k: v for k, v in query.items() if v is not None}


def _keys_to_press(G, source, targets):
    from networkx import NetworkXNoPath
    from networkx.algorithms.shortest_paths.generic import shortest_path

    assert targets

    paths = []
    for t in targets:
        try:
            paths.append(shortest_path(
                G, source=source, target=t, weight="weight"))
        except NetworkXNoPath:
            pass
    if not paths:
        raise NetworkXNoPath("No path to %s." % (
            _join_with_commas([str(t) for t in targets], last_one=" or ")))
    paths.sort(key=lambda p: _path_weight(G, p))
    path = paths[0]
    # shortest_path(G, "A", "V") -> ["A", "H", "O", "V"]
    # shortest_path(G, "A", "A") -> ["A"]
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


def _path_weight(G, path):
    if len(path) == 1:
        return 0
    total = 0
    for s, t in zip(path[:-1], path[1:]):
        total += G[s][t].get("weight", 1)
    return total


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
    from networkx import DiGraph

    G_ = DiGraph()
    for node in G.nodes():
        G_.add_node(node)
    for u, v, data in G.edges(data=True):
        if data["key"] == "KEY_OK" and u.text:
            continue
        G_.add_edge(u, v, **data)
    return G_


def _reshape_array(a, cols, rows):
    """
    >>> _reshape_array("abcdefghijklmnopqrstuvwxyz1234567890", 7, 5)
    ['abcdefg',
     'hijklmn',
     'opqrstu',
     'vwxyz12',
     '3456789']
    """
    out = []
    for y in range(rows):
        out.append(a[y * cols:(y + 1) * cols])
    return out


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
