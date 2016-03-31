# coding=utf-8


def hello():
    r"""
    Basics:

    >>> True
    True
    >>> False
    False
    >>> None
    >>> print
    <BLANKLINE>
    >>> print "Hello"
    Hello
    >>> a = "hello"
    >>> raise Exception("bye-bye")
    Traceback (most recent call last):
    Exception: bye-bye

    Unicode:

    >>> print "Spın̈al Tap"
    Spın̈al Tap
    >>> print u"Spın̈al Tap"  # doctest: +SKIP
    Sp\xc4\xb1n\xcc\x88al Tap
    >>> print u"Spinal Tap"
    Spinal Tap
    >>> "Spın̈al Tap"
    'Sp\xc4\xb1n\xcc\x88al Tap'
    >>> u"Spın̈al Tap"
    u'Sp\xc4\xb1n\xcc\x88al Tap'
    >>> raise Exception("Spın̈al Tap")
    Traceback (most recent call last):
    Exception: Spın̈al Tap
    >>> raise Exception(u"Spın̈al Tap")
    Traceback (most recent call last):
    Exception: Sp\xc4\xb1n\xcc\x88al Tap

    Removal of uninteresting tests:

    >>> True
    True
    >>> raise Exception("FORE! I mean FIVE! I mean FIRE!")
    Traceback (most recent call last):
    Exception: FORE! I mean FIVE! I mean FIRE!
    >>> print "hello"
    hello
    """
    pass
