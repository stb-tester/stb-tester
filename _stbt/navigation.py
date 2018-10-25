from _stbt.types import Region
from _stbt.transition import press_and_wait


def _as_region(obj):
    if isinstance(obj, Region):
        return obj
    try:
        return obj.selection.region
    except AttributeError:
        return obj.region


class NavigationFailed(AssertionError):
    def __init__(self, page, initial_region, to_region, current_region,
                 key_choices):
        super(self, NavigationError).__init__(self, "Navigation Failed")
        self.page = page
        self.initial_region = initial_region
        self.to_region = to_region
        self.current_region = current_region
        self.key_choices = key_choices

    def __str__(self):
        return ("Navigation failed: Attempted to get to %r from %r but "
                "pressing keys %r had no effect once selection reached "
                "position %r") % (
        self.to_region, self.initial_region, self.key_choices,
        self.current_region)


def navigate_fixed_layout(page, to_region):
    """Used to navigate menus where the selection moves on the page, but the
    page itself doesn't scroll.  This means the item you're navigating to
    doesn't move in response to pressing the direction keys.

    This function will use keys 'KEY_UP', 'KEY_DOWN', 'KEY_LEFT' and 'KEY_RIGHT'
    as appropriate depending on the relative location of `page.selection.region`
    and `to_region`.

    Limitations:

    * This function uses `press_and_wait()` for navigating so is not suitable
      for screens with animation including screens with picture-in-picture and
      live-tv behind transparency.

    Example use:

    This is a method within a `FrameObject` to select the button marked TV:

        def select_tv(self)
            return navigate_fixed_layout(
                self, stbt.match_text("TV", frame=self._frame))

    :param FrameObject page: The current frame object.
    :param Region to_region: The location to navigate to.

    :returns: The FrameObject corresponding to navigation being complete.  This
        may be the same object passed in as `page` if the `to_region` is already
        selected.  Typically this will be of the same type as `page` depending
        on the implementation of `page.refresh()`.
    :rtype: FrameObject
    """
    destination = _as_region(destination)
    current = initial_region = _as_region(page)

    while True:
        current = _as_region(page)
        if Region.intersect(destination, current):
            return page
        keys = set()
        if destination.right < current.x:
            keys.add('KEY_LEFT')
        elif current.right < destination.x:
            keys.add('KEY_RIGHT')
        if destination.bottom < current.y:
            keys.add('KEY_UP')
        elif current.bottom < destination.y:
            keys.add('KEY_DOWN')

        key_choices = tuple(keys)
        t = None
        while keys:
            key = random.choice(keys)
            keys.remove(key)
            t = press_and_wait(key)
            if t:
                break
        else:
            raise NavigationError(page, initial_region, to_region,
                                  current_region, key_choices)

        page = page.refresh(t.frame)
        assert page, ("navigate_fixed_layout: Invalid Page %r for frame at "
                      "time %f after pressing key %r") % (page, frame.time, key)
