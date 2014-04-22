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
