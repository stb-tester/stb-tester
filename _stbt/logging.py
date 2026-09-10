import argparse
import dataclasses
import itertools
import logging
import os
import sys
import typing
from collections import namedtuple, OrderedDict
from contextlib import contextmanager
from textwrap import dedent

from .config import get_config
from .types import Region, RegionT, Size
from .utils import mkdir_p

if typing.TYPE_CHECKING:
    import numpy
    import numpy.typing
    import traceback
    from .core import SinkPipeline
    from .imgutils import FrameT


_debug_level: "int | None" = None

# Running in a Jupyter Notebook:
_jupyter_logging_enabled = "JPY_PARENT_PID" in os.environ

logger = logging.getLogger("stbt")
trace_logger = logging.getLogger("stbt.trace")


def init_logger():
    if logger.handlers:
        logger.warning("stbt logger already initialised", stack_info=True)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


def debug(msg: str, *args, **kwargs):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if get_debug_level() > 0:
        logger.debug(msg, *args, **kwargs)


def ddebug(s):
    """Extra verbose debug for stbt developers, not end users"""
    if get_debug_level() > 1:
        trace_logger.debug(s)


def warn(msg: str, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)


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
        help='Enable debug output (specify twice to enable detailed '
             'dumps to ./stbt-debug directory)')


def imshow(img, regions=None):
    """Displays the image in a Jupyter Notebook Notebook.

    You can only call this if you're already inside a Jupyter Notebook.
    """
    if "JPY_PARENT_PID" not in os.environ:
        raise RuntimeError(
            "_stbt.logging.imshow can only be run inside a Jupyter Notebook")

    import cv2

    if regions:
        from _stbt.imgutils import load_image
        img = load_image(img)
        for r in regions:
            cv2.rectangle(img, (r.x, r.y), (r.right, r.bottom), (32, 0, 255))

    from IPython.core.display import Image, display
    if isinstance(img, str):
        display(Image(img))
    else:
        _, data = cv2.imencode(".png", img)
        display(Image(data=bytes(data.data), format="png"))


preserve_loggers = False
image_loggers: "list[ImageLogger]" = []


# Intended to be overridden externally to remove uninteresting frames from the
# stack if necessary:
def filter_traceback(
        stack_frames: "typing.Sequence[traceback.FrameSummary]",
) -> "typing.Sequence[traceback.FrameSummary]":
    return stack_frames


@dataclasses.dataclass
class _ImageMeta:
    description: str
    height: int
    width: int
    # The region of the source image that this image was derived from, if any.
    # Usually this will be the same size as the source image, but for example a
    # heatmap from `match` will be smaller.
    source_region: "Region | None"


class ImageLogger():
    """Log intermediate images used in image processing (such as `match`).

    Create a new ImageLogger instance for each frame of video.
    """
    _frame_number = itertools.count(1)

    def __init__(self, name: str, **kwargs):
        self.jupyter = _jupyter_logging_enabled
        self.enabled = get_debug_level() > 1 or self.jupyter
        self.data = {}
        if not self.enabled:
            return

        import traceback

        self.name = name
        self.frame_number = next(ImageLogger._frame_number)
        self.call_stack = filter_traceback(traceback.extract_stack()[:-2])

        if preserve_loggers:
            # Store this for the summary later
            image_loggers.append(self)

        self.images: "OrderedDict[str, FrameT]" = OrderedDict()
        self.image_annotations: "dict[str, list]" = {}
        self.image_meta: dict[str, _ImageMeta] = {}

        outdir = os.path.join("stbt-debug", "%05d" % self.frame_number)
        try:
            mkdir_p(outdir)
            self.outdir = outdir
        except OSError:
            warn("Failed to create directory '%s'; won't save debug images."
                 % outdir)
            self.enabled = False
            return

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

    def imwrite(
            self,
            name: str,
            image: "numpy.typing.NDArray | None",
            regions: "list[Region] | Region | None" = None,
            colours: "list[tuple[int, int, int]] | tuple[int, int, int] | None" = None,  # pylint: disable=line-too-long
            scale: float = 1,
            *,
            description: str = "",
            source_region: "Region | None | str" = None,
    ):
        import cv2
        import numpy
        if not self.enabled:
            return
        if image is None:
            return
        if name in self.images:
            raise ValueError("Image for name '%s' already logged" % name)
        if image.dtype == numpy.float32:
            # Scale `cv2.matchTemplate` heatmap output in range
            # [0.0, 1.0] to visible grayscale range [0, 255].
            image = cv2.convertScaleAbs(image, alpha=255.0 / scale)
            assert isinstance(image, numpy.ndarray)
        else:
            image = image.copy()
        if isinstance(source_region, str):
            source_region = self.data[source_region]
            assert isinstance(source_region, (Region, type(None)))
        if name == "frame":
            if not description:
                description = (
                    "Original uncropped source frame originally captured from "
                    "the device under test")
            if not source_region:
                source_region = Region(0, 0, image.shape[1], image.shape[0])
        assert image is not None
        self.images[name] = image
        self.image_meta[name] = _ImageMeta(
            description=description,
            height=image.shape[0],
            width=image.shape[1],
            source_region=source_region,
        )
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

        test_pack_root = None
        try:
            from stbt_core import TEST_PACK_ROOT
            test_pack_root = TEST_PACK_ROOT
        except (ImportError, AttributeError):
            pass
        assert test_pack_root is None or os.path.isabs(test_pack_root)

        template_kwargs = self.data.copy()
        template_kwargs["images"] = self.images
        template_kwargs.update(kwargs)

        index_html = os.path.join(self.outdir, "index.html")
        with open(index_html, "w", encoding="utf-8") as f:
            f.write(jinja2.Template(_INDEX_HTML_HEADER)
                    .render(frame_number=self.frame_number,
                            jupyter=self.jupyter))
            f.write(jinja2.Template(dedent(template.lstrip("\n")))
                    .render(annotated_image=self._draw_annotated_image,
                            draw=self._draw,
                            img=self._img,
                            jupyter=self.jupyter,
                            **template_kwargs))
            f.write(jinja2.Template(_INDEX_HTML_FOOTER, autoescape=True)
                    .render(call_stack=self.call_stack,
                            test_pack_root=test_pack_root,
                            relpath_under=relpath_under,
                            is_under=_is_under,
                            ))

        if self.jupyter:
            from IPython.display import display, IFrame
            display(IFrame(src=index_html, width=974, height=600))

    @staticmethod
    def _draw(region: RegionT, source_size: Size, css_class, title=None):
        import jinja2

        if region is None:
            return ""

        if isinstance(css_class, bool):
            if css_class:
                css_class = "matched"
            else:
                css_class = "nomatch"

        if title:
            import markupsafe
            title_html = markupsafe.Markup("<br>").join(title.splitlines())
        else:
            title_html = None

        return jinja2.Template(dedent("""\
            <div class="region {{css_class}}{{ ' has-tooltip' if title_html else '' }}"
                 style="left: {{region.x / image.width * 100}}%;
                        top: {{region.y / image.height * 100}}%;
                        width: {{region.width / image.width * 100}}%;
                        height: {{region.height / image.height * 100}}%"
                 >{% if title_html %}<div class="tooltip">{{ title_html }}</div>{% endif %}</div>
            """)) \
            .render(css_class=css_class,
                    image=source_size,
                    region=region,
                    title=title,
                    title_html=title_html,
                    )

    def _img(
            self,
            name: str,
            *,
            desc_suffix: str = "",
            classes: str = "",
    ) -> str:
        import markupsafe
        if name not in self.images:
            warn("ImageLogger: No image named '%s'" % name)
            return ""
        meta = self.image_meta[name]
        title = meta.description
        if meta.source_region and name != "frame":
            src = self.image_meta["frame"]
            if meta.source_region == Region(0, 0, src.width, src.height):
                title += (
                    "\n\nThis image was derived from the source frame without "
                    "cropping.")
            else:
                title += (
                    "\n\nThis image was derived from the source frame by "
                    "cropping to the region %s." % (meta.source_region,))
        if desc_suffix:
            title += "\n\n" + desc_suffix
        return markupsafe.Markup(
            '<img class="img-%s %s" src="%s.png" title="%s" height="%d" '
            'width="%d">') % (
            name, classes, name, title, meta.height, meta.width)

    def _draw_annotated_image(self, regions=None, source_name="frame"):
        import jinja2

        s = self.images[source_name].shape
        source_size = Region(0, 0, s[1], s[0])

        _regions: list[tuple[RegionT, str | bool | None, str | None]] = []
        if "region" in self.data and source_name == "frame":
            _regions.append((Region.intersect(self.data["region"], source_size),
                             "source_region", None))

        if regions is None:
            regions = []
        elif not isinstance(regions, list):
            regions = [regions]
        for r in regions:
            if isinstance(r, Region):
                _regions.append((r, "matched", None))
            elif hasattr(r, "region"):  # e.g. MotionResult
                _regions.append((r.region, "matched" if r else "nomatch", None))
            elif isinstance(r, tuple) and len(r) == 3:
                _regions.append(r)
            else:
                warn("ImageLogger._draw_annotated_image: Expected Region, "
                     "Match/MotionResult, or 3-tuple (region, css_class, title)"
                     "; got %r" % (r,))

        # Ensure regions are in a deterministic order. Where a region is None,
        # we sort it as though it were the whole source image.
        _regions = sorted(_regions, key=lambda el: (el[0] or source_size))

        self.image_annotations[source_name] = [
            {"region": region, "title": title} for region, _, title in _regions]

        desc_suffix = ""
        if _regions:
            desc_suffix = (
                "This image is annotated with the following regions:\n\n" +
                "\n".join(
                    "* %s: %s class: %s" % (
                        (title or "Region").replace("\n", " "),
                        region,
                        css_class)
                    for region, css_class, title in _regions))

        return jinja2.Template(dedent("""\
            <div class="annotated_image">
              {{ img(source_name, desc_suffix=desc_suffix) }}
              {% for region, css_class, title in regions %}
              {{ draw(region, source_size, css_class, title) }}
              {% endfor %}
            </div>
        """)).render(
            img=self._img,
            draw=self._draw,
            regions=_regions,
            source_name=source_name,
            source_size=source_size,
            desc_suffix=desc_suffix,
        )


_INDEX_HTML_HEADER = dedent(
    """\
    <!DOCTYPE html>
    <html lang='en'>
    <head>
    <meta charset="utf-8"/>
    <link href="https://stb-tester.com/assets/bootstrap-3.3.2.min.css" rel="stylesheet">
    <style>
        a.nav { margin: 10px; }
        a.nav.pull-left { margin-left: 0; }
        a.nav.pull-right { margin-right: 0; }
        h5 { margin-top: 40px; }
        .annotated_image { position: relative; display: inline-block; }
        .annotated_image img { max-width: 100%; width: auto; height: auto; }
        .region { position: absolute; pointer-events: none; }
        .region.has-tooltip { pointer-events: auto; }
        .region .tooltip {
            visibility: hidden;
            background-color: #333;
            color: #fff;
            text-align: center;
            border-radius: 4px;
            padding: 5px;
            position: absolute;
            z-index: 1;
            bottom: calc(100% + 5px);
            left: 0;
            right: 0;
            margin-left: auto;
            margin-right: auto;
            opacity: 0;
            transition: opacity 0.3s;
            width: max-content;
            max-width: 300px;
        }
        .region:hover .tooltip { visibility: visible; opacity: 1; }
        .source_region { outline: 2px solid #8080ff; }
        .region.matched { outline: 2px solid #ff0020; }
        .region.nomatch { outline: 2px solid #ffff20; }

        /* match */
        .table th { font-weight: normal; background-color: #eee; }
        img.thumb {
            vertical-align: middle; max-width: 150px; max-height: 36px;
            width: auto; height: auto;
            padding: 1px; border: 1px solid #ccc; }
        .table td { vertical-align: middle; }
    </style>
    </head>
    <body>
    <div class="container-fluid">
    {% if not jupyter %}
    {%   if frame_number > 1 %}
    <a href="../{{ "%05d" % (frame_number - 1) }}/index.html"
       class="nav pull-left">«prev</a>
    {%   endif %}
    <a href="../{{ "%05d" % (frame_number + 1) }}/index.html"
       class="nav pull-right">next»</a>
    {% endif %}
    """)


def relpath_under(path: str, start: str):
    if path.startswith("<"):
        # Probably not a real python source file:
        return path
    rel = os.path.relpath(path, start)
    if rel.startswith(".."):
        return os.path.abspath(path)
    else:
        return rel


def _is_under(path: str, start: str):
    return (not path.startswith('<') and
            not os.path.relpath(path, start).startswith(".."))


_INDEX_HTML_FOOTER = dedent("""\
    <h2>Call stack</h2>
    <pre>Traceback (most recent call last):
{% for filename, lineno, funcname, text in call_stack %}{% set user_code = is_under(filename, test_pack_root) %}{% if loop.changed(user_code) %}<{% if not user_code %}/{% endif %}b>{% endif %}  File "{{ relpath_under(filename, test_pack_root) }}", line {{ lineno }}, in {{ funcname }}
    {{ text }}
{% endfor %}</pre>
    </div>
    </body>
    </html>
""")


def draw_on(frame, *args, **kwargs):
    draw_sink_ref = getattr(frame, '_draw_sink', None)
    if not draw_sink_ref:
        return
    draw_sink: "SinkPipeline | None" = draw_sink_ref()
    if not draw_sink:
        return
    draw_sink.draw(*args, **kwargs)


def draw_source_region(frame, region):
    draw_on(frame, SourceRegion(region, getattr(frame, "time", None)))


class SourceRegion(typing.NamedTuple):
    region: Region
    time: "float | None"


class _Annotation(namedtuple("_Annotation", "time region label colour")):
    MATCHED = (32, 0, 255)  # Red
    NO_MATCH = (32, 255, 255)  # Yellow
    SOURCE_REGION = (255, 128, 128)  # Blue

    @staticmethod
    def from_result(result, label=""):
        if isinstance(result, SourceRegion):
            colour = _Annotation.SOURCE_REGION
        elif result:
            colour = _Annotation.MATCHED
        else:
            colour = _Annotation.NO_MATCH
        return _Annotation(result.time, result.region, label, colour)
