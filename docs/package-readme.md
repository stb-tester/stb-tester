# Stb-tester open-source APIs (stbt_core)

**Automated User Interface Testing for Set-Top Boxes & Smart TVs**

* Copyright © 2013-2023 Stb-tester.com Ltd,
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
