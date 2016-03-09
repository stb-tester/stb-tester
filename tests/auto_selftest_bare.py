# coding=utf-8


def hello():
    r"""
    Basics:

    >>> True
    >>> False
    >>> None
    >>> print
    >>> print "Hello"
    >>> a = "hello"
    >>> raise Exception("bye-bye")

    Unicode:

    >>> print "Spın̈al Tap"
    >>> print u"Spın̈al Tap"
    >>> print u"Spinal Tap"
    >>> "Spın̈al Tap"
    >>> u"Spın̈al Tap"
    >>> raise Exception("Spın̈al Tap")
    >>> raise Exception(u"Spın̈al Tap")

    Removal of uninteresting tests:

    >>> True # remove-if-false
    >>> False # remove-if-false
    >>> raise Exception("FORE! I mean FIVE! I mean FIRE!") # remove-if-false
    >>> print "hello" # remove-if-false
    >>> a = "hello" # remove-if-false
    """
    pass
