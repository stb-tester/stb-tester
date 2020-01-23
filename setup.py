# coding: utf-8

import setuptools


long_description = """\
# Stb-tester

**Automated User Interface Testing for Set-Top Boxes & Smart TVs**

* Copyright © 2013-2019 Stb-tester.com Ltd,
  2012-2014 YouView TV Ltd. and other contributors.
* License: LGPL v2.1 or (at your option) any later version (see [LICENSE]).

This package contains the "stbt" Python APIs that you can use in test-scripts
written for running on the [Stb-tester Platform](https://stb-tester.com).
The primary purpose of this package is to make the stbt library easy to
install locally for IDE linting & autocompletion.

This package doesn't support video-capture, so `stbt.get_frame()` and
`stbt.frames()` won't work -- but you will be able to run `stbt.match()` if you
specify the `frame` parameter explicitly, for example by loading a screenshot
from disk with `stbt.load_image()`.

This package doesn't include remote-control integrations, so `stbt.press()` and
similar functions won't work.

This package doesn't bundle the Tesseract OCR engine, so `stbt.ocr()` and
`stbt.match_text()` won't work.

[LICENSE]: https://github.com/stb-tester/stb-tester/blob/master/LICENSE
"""

setuptools.setup(
    name="stb-tester",
    version="31.1.5",
    author="Stb-tester.com Ltd.",
    author_email="support@stb-tester.com",
    description="Automated GUI testing for Set-Top Boxes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://stb-tester.com",
    packages=["stbt", "_stbt"],
    package_data={
        "_stbt": ["stbt.conf"],
    },
    classifiers=[
        # pylint:disable=line-too-long
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development :: Testing",
    ],
    # I have only tested Python 2.7 & 3.6
    python_requires=">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*",
    install_requires=[
        "astroid==1.6.0",
        "future==0.15.2",
        "Jinja2==2.10.1",
        "lxml==4.2",
        "networkx==1.11",
        "opencv-python~=3.2",
        "pylint==1.8.3",
        "stbt-premium-stubs~=31.0",
    ],
)
