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

"""

setuptools.setup(
    name="stb-tester",
    version="31.1",
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
        "future==0.15.2",
        "Jinja2==2.10",
        "lxml==4.2",
        "networkx==1.11",
        "numpy==1.13",
        "opencv-python~=3.2.0",
    ],
)
