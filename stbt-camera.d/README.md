* Point Logitech C920 webcam at TV screen. Note that the camera's firmware has
  a bug where it forgets the settings set previously via V4L controls. This is
  [fixed](https://git.kernel.org/cgit/linux/kernel/git/next/linux-next.git/log/?qt=grep&q=uvcvideo%3A+Work+around+buggy+Logitech+C920+firmware)
  in Linux kernel 3.18 and newer.
* Run `stbt --with-experimental camera calibrate` and follow the instructions.
  At the end of the calibration process this will write the calibration
  settings to your stbt configuration file.
* Run `stbt --with-experimental camera validate` to test the calibration
  settings.
* Use `stbt run` as usual to run your tests.
