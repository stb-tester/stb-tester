# stb-tester

**Automated User Interface Testing for Set-Top Boxes & Smart TVs**

* Copyright © 2013-2019 Stb-tester.com Ltd,
  2012-2014 YouView TV Ltd. and other contributors.
* License: LGPL v2.1 or (at your option) any later version (see [LICENSE]).
* <img src="https://github.com/stb-tester/stb-tester/actions/workflows/ubuntu2204.yml/badge.svg">

Stb-tester issues commands to the device-under-test in the same way a real user
does (typically using an infrared remote control).

Stb-tester then checks the behaviour of the device-under-test by analysing the
device's video output.

For an overview of stb-tester's capabilities, see the videos at
<https://stb-tester.com/videos/>.

Testcases are written in the Python programming language. They look like this:

    def test_that_i_can_tune_to_bbc_one_from_the_guide():
        stbt.press("KEY_EPG")
        stbt.wait_for_match("Guide.png")
        stbt.press("KEY_OK")
        stbt.wait_for_match("BBC One.png")
        stbt.wait_for_motion()

See the [Python API documentation] for more details.

For commercial support and turn-key test rigs, see <https://stb-tester.com>.

To build your own test rig hardware, and for community-supported documentation
and mailing list, see the [wiki], in particular [Getting Started].


[LICENSE]: https://github.com/stb-tester/stb-tester/blob/master/LICENSE
[Python API documentation]: http://stb-tester.com/manual/python-api
[wiki]: https://github.com/stb-tester/stb-tester/wiki
[Getting Started]: https://github.com/stb-tester/stb-tester/wiki/Getting-started-with-stb-tester
