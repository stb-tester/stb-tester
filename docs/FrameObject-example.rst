This demonstrates basic `FrameObject` usage.  The class below corresponds to
the dialog box we see in this image that we've captured from our set-top
box:

.. figure:: images/frame-object-with-dialog.png
   :alt: screenshot of dialog box
   :figwidth: 80%
   :align: center

We create a `class` deriving from the `FrameObject` base class.  The base
class provides a `self._frame` member.  The we define a set of properties,
each one extracting some information of interest from that frame.

.. testsetup::

    >>> from stbt import FrameObject, match, ocr, Region

>>> class Dialog(FrameObject):
...     @property
...     def is_visible(self):
...         """
...         All FrameObjects must define the `is_visible` property.  It will
...         determine the truthiness of the object.  Returning True from
...         this property indicates that this FrameObject class can be used
...         with the provided frame and that the values of the other
...         properties are likely to be valid.
...
...         In this example we only return True if we see the info icon
...         that appears on each dialog box.
...
...         It's a good idea to return simple types from these properties
...         rather than `MatchResult`s to make the ``__repr__`` cleaner and
...         to preserve equality properties.
...         """
...         return bool(self._info)
...
...     @property
...     def title(self):
...         """
...         This property demonstrates an advantage of Frame Objects over
...         just including the code in the test directly.  Test code can now
...         write:
...
...             assert Dialog().title == "Information"
...
...         rather than:
...
...             assert (stbt.ocr(region=stbt.Region(396, 249, 500, 50)) ==
...                     "Information"
...
...         A lot more intention revealing, and if the position of the title
...         moves there is just one place in your test-pack that needs to be
...         updated.
...         """
...         return ocr(region=Region(396, 249, 500, 50), frame=self._frame)
...
...     @property
...     def message(self):
...         """
...         This property demonstrates an advantage of Frame Objects over
...         helper functions.  We are using the position of the info icon to
...         find this message.  Because the private `_info` property is
...         shared between this property and `is_visible` we don't need to
...         compute it twice.
...
...         When defining Frame Objects you must take care to pass
...         `self._frame` into every call to an image processing function.
...         """
...         right_of_info = Region(
...             x=self._info.region.right, y=self._info.region.y,
...             width=390, height=self._info.region.height)
...         return (ocr(region=right_of_info, frame=self._frame)
...                 .replace('\n', ' '))
...
...     @property
...     def _info(self):
...         """
...         This is a private property because its name starts with `_`.  It
...         will not appear in `__repr__` or count toward equality
...         comparisons, but the result from it will still be memoized.
...         This is useful to share intermediate values between your public
...         properties, particularly if they are expensive to calculate.  In
...         this instance we will be sharing the result between `is_visible`
...         and `message`.
...
...         You wouldn't want this to be a public property because it
...         returns a `MatchResult` which incorporates the whole of the
...         frame passed into `match`.
...         """
...         return match('../tests/info.png', frame=self._frame)

In the examples below we always pass a frame into the constructor.  In
practice you're unlikely to do so: the base class will just grab one from
the device-under-test.  This allows constructions like::

    dialog = wait_until(Dialog)
    assert 'great' in dialog.message

But we can also explicitly pass in a frame.  The examples below will make
use of these example frames:

>>> from tests.test_frame_object import _load_frame
>>> dialog = Dialog(frame=_load_frame('with-dialog'))
>>> dialog_fab = Dialog(frame=_load_frame('with-dialog2'))
>>> no_dialog = Dialog(frame=_load_frame('without-dialog'))
>>> dialog_bunnies = Dialog(_load_frame('with-dialog-different-background'))
>>> no_dialog_bunnies = Dialog(_load_frame(
...     'without-dialog-different-background'))

.. |dialog| image:: images/frame-object-with-dialog.png
   :alt: screenshot of dialog box
   :width: 250px

.. |dialog_fab| image:: images/frame-object-with-dialog2.png
   :alt: screenshot of dialog box
   :width: 250px

.. |no_dialog| image:: images/frame-object-without-dialog.png
   :alt: screenshot of dialog box
   :width: 250px

.. |dialog_bunnies| image:: images/frame-object-with-dialog-different-background.png
   :alt: screenshot of dialog box
   :width: 250px

.. |no_dialog_bunnies| image:: images/frame-object-without-dialog-different-background.png
   :alt: screenshot of dialog box
   :width: 250px

+---------------------+---------------------+
| dialog              | no_dialog           |
|                     |                     |
| |dialog|            | |no_dialog|         |
+---------------------+---------------------+
| dialog_bunnies      | no_dialog_bunnies   |
|                     |                     |
| |dialog_bunnies|    | |no_dialog_bunnies| |
+---------------------+---------------------+
| dialog_fab          |                     |
|                     |                     |
| |dialog_fab|        |                     |
+---------------------+---------------------+

Some basic operations:

>>> print dialog.message
This set-top box is great
>>> print dialog_fab.message
This set-top box is fabulous

`FrameObject` defines truthiness of your objects based on the mandatory
`is_visible` property:

>>> bool(dialog)
True
>>> bool(no_dialog)
False

And if `is_visible` is `False` all the rest of the properties will be
`None`.

>>> print no_dialog.message
None

This enables usage like::

    assert wait_until(lambda: Dialog().title == 'Information')

FrameObject defines `__repr__` so you don't have to:

>>> dialog
Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')
>>> dialog_fab
Dialog(is_visible=True, message=u'This set-top box is fabulous', title=u'Information')
>>> no_dialog
Dialog(is_visible=False)

Making doctests far more convenient to write (or generate).

Frame Objects with identical property values are equal, even if the backing
images are not:

>>> assert dialog == dialog
>>> assert dialog == Dialog(_load_frame('with-dialog'))
>>> assert dialog == dialog_bunnies
>>> assert dialog != dialog_fab
>>> assert dialog != no_dialog

And all `False` ish frame objects of the same type are equal:

>>> assert no_dialog == no_dialog
>>> assert no_dialog == no_dialog_bunnies

FrameObject defines `__hash__` too so you can store them in a `set`:

>>> {dialog}
set([Dialog(is_visible=True, message=u'This set-top box is great', title=u'Information')])
>>> len({no_dialog, dialog, dialog, dialog_bunnies})
2

And it defines ordering for you:

>>> dialog < dialog_bunnies
False
>>> dialog_bunnies < dialog
False
>>> dialog_fab < dialog
True
