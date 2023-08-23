# coding: utf-8

# import setuptools
from setuptools import setup, Extension

long_description = """\
# Stb-tester open-source APIs (stbt_core)

**Automated User Interface Testing for Set-Top Boxes & Smart TVs**

* Copyright © 2013-2021 Stb-tester.com Ltd,
  2012-2014 YouView TV Ltd. and other contributors.
* License: LGPL v2.1 or (at your option) any later version (see [LICENSE]).

This package contains the `stbt_core` open-source Python APIs that you can use
in test-scripts written for running on the [Stb-tester Platform]. The primary
purpose of this package is to make the `stbt_core` library easy to install
locally for IDE linting & autocompletion.

This package doesn't support video-capture, so `get_frame()` and `frames()`
won't work -- but you will be able to run `match()` if you specify the `frame`
parameter explicitly, for example by loading a screenshot from disk with
`load_image()`.

This package doesn't include remote-control integrations, so `press()` and
similar functions won't work.

This package doesn't bundle the Tesseract OCR engine, so `ocr()` and
`match_text()` won't work.

[LICENSE]: https://github.com/stb-tester/stb-tester/blob/master/LICENSE
[Stb-tester Platform]: https://stb-tester.com
"""
extentions = [Extension('_stbt.libstbt',
                        sources=['_stbt/sqdiff.c'],
                        extra_compile_args=["-std=c99"],
                        ),
              Extension('_stbt.libxxhash',
                        sources=['_stbt/xxhash.c'],
                        depends=['_stbt/xxhash.h'],
                        extra_compile_args=["-std=c99"],
                        )
              ]
setup(
    name="stbt_core",
    version="133.0.0",
    author="Stb-tester.com Ltd.",
    author_email="support@stb-tester.com",
    description="Automated GUI testing for Set-Top Boxes, with MacOS and Linux MOD",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://stb-tester.com",
    packages=["stbt_core", "_stbt"],
    package_data={
        "_stbt": ["stbt.conf", "sqdiff.c", "xorg.conf.in", "xxhash.c", "xxhash.h"],  # , "libstbt.so", "libxxhash.so",
    },
    ext_modules=extentions,
    classifiers=[
        # pylint:disable=line-too-long
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.6",
    extras_require={
        "ocr": ["lxml==4.8.0"],
        "debug": ["Jinja2==3.0.3"],
        "keyboard": ["networkx==2.4"],
    },
    install_requires=[
        "astroid==2.11.6",
        "attrs==22.2.0",
        "isort==5.6.4",
        "opencv-python~=4.5",
        "pylint~=2.13.0",
    ],
)
