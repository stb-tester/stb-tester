#include "gstmotiondetect.h"
#include "gsttemplatematch.h"

#include <gst/gst.h>


static gboolean
plugin_init (GstPlugin * plugin)
{
  if (!gst_element_register (plugin, "stbt-motiondetect", GST_RANK_NONE,
          gst_motiondetect_get_type()))
    return FALSE;

  if (!gst_element_register (plugin, "stbt-templatematch", GST_RANK_NONE,
          gst_templatematch_get_type()))
    return FALSE;

  return TRUE;
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    "stb-tester",
    "GStreamer elements used by stb-tester",
    plugin_init, VERSION, "LGPL",
    "gst-stb-tester" /*GST_PACKAGE_NAME*/,
    "http://stb-tester.com" /*GST_PACKAGE_ORIGIN*/)
