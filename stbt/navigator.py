# Copyright 2016-2017 Stb-tester.com Ltd.

import sys

from enum import Enum

import stbt


class Direction(Enum):
    VERTICAL = 0
    HORIZONTAL = 1


class FixedFocusNavigator(object):
    """
    Helps navigating a "fixed focus" menu where the "selection" or "highlight"
    doesn't move, but the menu items scroll into the selection position.

    Takes care of:

    * Pressing
    * Waiting for the selection to change
    * Waiting for the selection to finish changing
    * Erroring if no progress is being made

    Example::

        import stbt.navigator
        nav = stbt.navigator.FixedFocusNavigator(
            MenuSelection,
            stbt.navigator.Direction.VERTICAL)
        nav.navigate_to(text="Settings")

    ...where ``MenuSelection`` is a `stbt.FrameObject` class and ``text`` is
    a property of that class that returns the current selection text.

    :param stbt.FrameObject frame_object: A ``FrameObject`` class (not an
        instance) that knows how to read the current selection, given a
        frame of video. When you call ``FixedFocusNavigator.navigate_to``
        you specify which property of the frame object to read.

    :param stbt.navigator.Direction direction: The direction of the menu:
        Either ``Direction.VERTICAL`` (navigated by pressing KEY_UP and
        KEY_DOWN) or ``Direction.HORIZONTAL`` (navigated by pressing
        KEY_LEFT and KEY_RIGHT).

    :param list items: An optional list of the items that you expect to
        see in the menu. Allows the navigator to decide whether to press
        up or down. Required if your menu doesn't wrap around.

    :param int max_items: Give up after pressing this number of times (note
        that we might give up earlier if we detect that the menu has wrapped
        around).

    :param current: An instance of the ``frame_object`` class specified
        earlier, representing the device-under-test's current state. If
        not given, we'll grab a new frame from the device-under-test and
        construct a new instance.

    """

    def __init__(self, frame_object, direction=Direction.VERTICAL, items=None,
                 max_items=100, current=None, dut=None, time=None):

        self.frame_object = frame_object
        if direction == Direction.VERTICAL:
            self.next_key = "KEY_DOWN"
            self.prev_key = "KEY_UP"
        else:
            self.next_key = "KEY_RIGHT"
            self.prev_key = "KEY_LEFT"
        self.items = items or []
        self.max_items = max_items

        if dut is not None:
            self._dut = dut
        else:
            self._dut = getattr(current, "_dut", None) or stbt._dut  # pylint:disable=protected-access

        if current is not None:
            self.current = current
        else:
            self.current = self.frame_object(frame=self._dut.get_frame())
        assert self.current

        if time is not None:
            # For greater testability
            self.time = time
        else:
            import time
            self.time = time.time

    def navigate_to(self, **kwargs):
        """Navigate to the specified menu item.

        The target must be specified as a keyword argument, for example
        ``text="Settings"``. The navigator will look for the 

        """

        if len(kwargs) != 1:
            raise ValueError(
                "navigate_to takes a single keyword argument that is the name "
                "of a FrameObject property")
        property_name, target = kwargs.items()[0]
        original_value = getattr(self.current, property_name)

        if self.items and target in self.items and original_value in self.items:
            if self.items.index(target) - self.items.index(original_value) > 0:
                key = self.next_key
            else:
                key = self.prev_key
        else:
            # If you don't specify the list of menu items, we assume the menu
            # wraps around and hope for the best.
            key = self.next_key

        for _ in range(self.max_items):
            assert self.current
            current_value = getattr(self.current, property_name)
            if current_value == target:
                sys.stderr.write("navigate_to: Found %s\n" % target)
                return self.current

            sys.stderr.write(
                "navigate_to: target=%r, current=%r, going to press %r\n"
                % (target, current_value, key))
            tr = press_and_wait(key, region=self.current.region)

            # In the future these needn't be assertions: We can cope with the
            # value not changing and try going in the opposite direction
            assert tr
            current = self.frame_object(frame=tr.frame)
            assert current and getattr(current, property_name) != current_value

            self.current = current

            assert getattr(self.current, property_name) != original_value, (
                "navigate_to wrapped around back to %s '%s' "
                "without finding '%s'"
                % (property_name, original_value, target))

        assert False, "Didn't find %s '%s' within %s presses" % (
            property_name, target, self.max_items)
