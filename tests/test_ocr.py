# coding: utf-8

import codecs
import sys
from textwrap import dedent

import cv2
from nose.tools import eq_

import stbt

sys.stdout = codecs.getwriter('utf8')(sys.stdout)


def test_that_ocr_returns_unicode():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/unicode.png'))
    assert isinstance(text, unicode)


def test_that_ocr_reads_unicode():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/unicode.png'), lang='eng+deu')
    eq_(u'£500\nRöthlisberger', text)


def test_that_ocr_can_read_small_text():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/small.png'))
    eq_(u'Small anti-aliased text is hard to read\nunless you magnify', text)


ligature_text = dedent(u"""\
    All the similar "quotes" and "quotes",
    'quotes' and 'quotes' should be recognised.

    For the avoidance of sillyness so should the
    ligatures in stiff, filter, fluid, affirm, afflict,
    and adrift.

    normal-hyphen, non-breaking hyphen,
    figure-dash, en-dash, em-dash,
    horizontal-bar.""")


def test_that_ligatures_and_ambiguous_punctuation_are_normalised():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png'))
    text = text.replace("horizonta|", "horizontal")  # for tesseract < 3.03
    eq_(ligature_text, text)


def test_that_setting_config_options_has_an_effect():
    # Unfortunately there are many tesseract config options and they are very
    # complicated so it's difficult to write a test that tests that a config
    # option is having the correct effect.  Due to the difficulty in determining
    # "correctness" instead here we test that setting a config option has an
    # effect at all.  This at least excercises our code which sets config
    # options.  I'm not happy about this and I hope to be able to replace this
    # once we have more experience with these settings in the real world.
    assert (stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png'),
                     tesseract_config={"tessedit_create_hocr": 1}) !=
            stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png')))
