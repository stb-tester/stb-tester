# coding: utf-8

from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order
import argparse
import itertools
import os
import sys
from collections import namedtuple, OrderedDict
from contextlib import contextmanager
from textwrap import dedent

from .config import get_config
from .types import Region
from .utils import mkdir_p

_debug_level = None


def debug(msg):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if get_debug_level() > 0:
        sys.stderr.write(
            "%s: %s\n" % (os.path.basename(sys.argv[0]), msg))


def ddebug(s):
    """Extra verbose debug for stbt developers, not end users"""
    if get_debug_level() > 1:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), s))


def warn(s):
    sys.stderr.write("%s: warning: %s\n" % (
        os.path.basename(sys.argv[0]), s))


def get_debug_level():
    global _debug_level
    if _debug_level is None:
        _debug_level = get_config('global', 'verbose', type_=int)
    return _debug_level


@contextmanager
def scoped_debug_level(level):
    global _debug_level
    oldlevel = _debug_level
    _debug_level = level
    try:
        yield
    finally:
        _debug_level = oldlevel


def argparser_add_verbose_argument(argparser):
    class IncreaseDebugLevel(argparse.Action):
        num_calls = 0

        def __call__(self, parser, namespace, values, option_string=None):
            global _debug_level
            self.num_calls += 1
            _debug_level = self.num_calls
            setattr(namespace, self.dest, _debug_level)

    argparser.add_argument(
        '-v', '--verbose', action=IncreaseDebugLevel, nargs=0,
        default=get_debug_level(),  # for stbt-run arguments dump
        help='Enable debug output (specify twice to enable GStreamer element '
             'dumps to ./stbt-debug directory)')


class ImageLogger(object):
    """Log intermediate images used in image processing (such as `match`).

    Create a new ImageLogger instance for each frame of video.
    """
    _frame_number = itertools.count(1)

    def __init__(self, name, **kwargs):
        self.enabled = get_debug_level() > 1
        if not self.enabled:
            return

        self.name = name
        self.frame_number = next(ImageLogger._frame_number)

        try:
            outdir = os.path.join("stbt-debug", "%05d" % self.frame_number)
            mkdir_p(outdir)
            self.outdir = outdir
        except OSError:
            warn("Failed to create directory '%s'; won't save debug images."
                 % outdir)
            self.enabled = False
            return

        self.images = OrderedDict()
        self.pyramid_levels = set()
        self.data = {}
        for k, v in kwargs.items():
            self.data[k] = v

    def set(self, **kwargs):
        if not self.enabled:
            return
        for k, v in kwargs.items():
            self.data[k] = v

    def append(self, **kwargs):
        if not self.enabled:
            return
        for k, v in kwargs.items():
            if k not in self.data:
                self.data[k] = []
            self.data[k].append(v)

    def imwrite(self, name, image, regions=None, colours=None, scale=1):
        import cv2
        import numpy
        if not self.enabled:
            return
        if image is None:
            return
        if name in self.images:
            raise ValueError("Image for name '%s' already logged" % name)
        if image is None:
            return
        if image.dtype == numpy.float32:
            # Scale `cv2.matchTemplate` heatmap output in range
            # [0.0, 1.0] to visible grayscale range [0, 255].
            image = cv2.convertScaleAbs(image, alpha=255.0 / scale)
        else:
            image = image.copy()
        self.images[name] = image
        if regions is None:
            regions = []
        elif not isinstance(regions, list):
            regions = [regions]
        if colours is None:
            colours = []
        elif not isinstance(colours, list):
            colours = [colours]
        for region, colour in zip(regions, colours):
            cv2.rectangle(
                image, (region.x, region.y), (region.right, region.bottom),
                colour, thickness=1)

        cv2.imwrite(os.path.join(self.outdir, name + ".png"), image)

    def html(self, template, **kwargs):
        if not self.enabled:
            return

        try:
            import jinja2
        except ImportError:
            warn(
                "Not generating html view of the image-processing debug images "
                "because python 'jinja2' module is not installed.")
            return

        template_kwargs = self.data.copy()
        template_kwargs["images"] = self.images
        template_kwargs.update(kwargs)

        with open(os.path.join(self.outdir, "index.html"), "w") as f:
            f.write(jinja2.Template(_INDEX_HTML_HEADER)
                    .render(frame_number=self.frame_number))
            f.write(jinja2.Template(dedent(template.lstrip("\n")))
                    .render(annotated_image=self._draw_annotated_image,
                            draw=self._draw,
                            **template_kwargs))
            f.write(jinja2.Template(_INDEX_HTML_FOOTER)
                    .render())

    def _draw(self, region, source_size, css_class, title=None):
        import jinja2

        if region is None:
            return ""

        if isinstance(css_class, bool):
            if css_class:
                css_class = "matched"
            else:
                css_class = "nomatch"

        return jinja2.Template(dedent("""\
            <div class="region {{css_class}}"
                 style="left: {{region.x / image.width * 100}}%;
                        top: {{region.y / image.height * 100}}%;
                        width: {{region.width / image.width * 100}}%;
                        height: {{region.height / image.height * 100}}%"
                 {% if title %}
                 title="{{ title | escape }}"
                 {% endif %}
                 ></div>
            """)) \
            .render(css_class=css_class,
                    image=source_size,
                    region=region,
                    title=title)

    def _draw_annotated_image(self, regions=None, source_name="source"):
        import jinja2

        s = self.images[source_name].shape
        source_size = Region(0, 0, s[1], s[0])

        _regions = []
        if "region" in self.data:
            _regions.append((Region.intersect(self.data["region"], source_size),
                             "source_region", None))

        if isinstance(regions, Region):
            _regions.append((regions, True, None))
        elif hasattr(regions, "region"):  # e.g. MotionResult
            _regions.append((regions.region, bool(regions), None))
        elif regions is not None:
            for r in regions:
                if not isinstance(r, tuple) or len(r) != 3:
                    raise ValueError(
                        "_draw_annotated_image expected 3-tuple "
                        "(region, css_class, title); got %r" % r)
                _regions.append(r)

        return jinja2.Template(dedent("""\
            <div class="annotated_image">
              <img src="{{source_name}}.png">
              {% for region, css_class, title in regions %}
              {{ draw(region, source_size, css_class, title) }}
              {% endfor %}
            </div>
        """)).render(
            draw=self._draw,
            regions=_regions,
            source_name=source_name,
            source_size=source_size,
        )


_INDEX_HTML_HEADER = dedent(u"""\
    <!DOCTYPE html>
    <html lang='en'>
    <head>
    <meta charset="utf-8"/>
    <link href="https://stb-tester.com/assets/bootstrap-3.3.2.min.css" rel="stylesheet">
    <style>
        a.nav { margin: 10px; }
        a.nav[href*="/00000/"] { visibility: hidden; }
        a.nav.pull-left { margin-left: 0; }
        a.nav.pull-right { margin-right: 0; }
        h5 { margin-top: 40px; }
        .annotated_image { position: relative; display: inline-block; }
        .annotated_image img { max-width: 100%; }
        .region { position: absolute; }
        .source_region { outline: 2px solid #8080ff; }
        .region.matched { outline: 2px solid #ff0020; }
        .region.nomatch { outline: 2px solid #ffff20; }

        /* match */
        .table th { font-weight: normal; background-color: #eee; }
        img.thumb {
            vertical-align: middle; max-width: 150px; max-height: 36px;
            padding: 1px; border: 1px solid #ccc; }
        .table td { vertical-align: middle; }
    </style>
    </head>
    <body>
    <div class="container">
    <a href="../{{ "%05d" % (frame_number - 1) }}/index.html"
       class="nav pull-left">«prev</a>
    <a href="../{{ "%05d" % (frame_number + 1) }}/index.html"
       class="nav pull-right">next»</a>

    """)

_INDEX_HTML_FOOTER = dedent(u"""\

    </div>
    </body>
    </html>
""")


def test_that_debug_can_write_unicode_strings():
    def test(level):
        with scoped_debug_level(level):
            warn(u'Prüfungs Debug-Unicode')
            debug(u'Prüfungs Debug-Unicode')
            ddebug(u'Prüfungs Debug-Unicode')
    for level in [0, 1, 2]:
        yield (test, level)


def draw_on(frame, *args, **kwargs):
    draw_sink_ref = getattr(frame, '_draw_sink', None)
    if not draw_sink_ref:
        return
    draw_sink = draw_sink_ref()
    if not draw_sink:
        return
    draw_sink.draw(*args, **kwargs)


class _Annotation(namedtuple("_Annotation", "time region label colour")):
    MATCHED = (32, 0, 255)  # Red
    NO_MATCH = (32, 255, 255)  # Yellow

    @staticmethod
    def from_result(result, label=""):
        colour = _Annotation.MATCHED if result else _Annotation.NO_MATCH
        return _Annotation(result.time, result.region, label, colour)
