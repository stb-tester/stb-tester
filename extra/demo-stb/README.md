A bare-bones HTML5 set-top box UI that can be used to demo stb-tester.

### To run

    make install-dependencies
    chromium-browser --no-sandbox --app=file://`pwd`/virtual-stb/index.html

(or use `stbt virtual-stb`).

### Known bugs

...that can be caught by demo tests.

* If you pause while the "play" patch is fading out, the "pause" patch doesn't
  appear.
* If you close the menu it forgets your current selection.
