/* Gstreamer element for motion detection (not motion tracking) using OpenCV.
 *
 * Copyright (C) 2012 YouView TV Ltd.
 * Author: David Rothlisberger <david@rothlis.net>
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 */

/**
 * SECTION:element-motiondetect
 *
 * If the #GstMotionDetect:enabled property is %TRUE, compares successive video
 * frames and sends a message named #motiondetect if it detects differences
 * between two frames.
 *
 * This element is used by stb-tester to check that video is playing (e.g.
 * after a channel change).
 *
 * The #motiondetect message's structure contains these fields:
 * - #gfloat #motiondetect.similarity: A number between 0 and 1.0 measuring
 *   the similarity between the latest frame and the previous frame.
 */

#include <gst/video/video.h>

#include "gstmotiondetect.h"


static GstStaticPadTemplate sinktemplate = GST_STATIC_PAD_TEMPLATE ("sink",
    GST_PAD_SINK,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_BGR));

static GstStaticPadTemplate srctemplate = GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_BGR));

GST_DEBUG_CATEGORY_STATIC (gst_motiondetect_debug);
#define GST_CAT_DEFAULT gst_motiondetect_debug

enum
{
    LAST_SIGNAL
};

enum
{
    PROP_0,
    PROP_ENABLED,
};

GST_BOILERPLATE (GstMotionDetect, gst_motiondetect, GstBaseTransform,
    GST_TYPE_BASE_TRANSFORM);

static void gst_motiondetect_finalize (GObject * object);
static void gst_motiondetect_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_motiondetect_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);

static GstFlowReturn gst_motiondetect_transform_ip (GstBaseTransform * trans,
    GstBuffer * buf);

static void
gst_motiondetect_base_init (gpointer gclass)
{
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (gclass);

  gst_element_class_set_details_simple (gstelement_class,
      "Motion detection",
      "Filter/Analyzer/Video",
      "Reports if any differences were found between successive frames",
      "David Rothlisberger <david@rothlis.net>");
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&srctemplate));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&sinktemplate));
}

static void
gst_motiondetect_class_init (GstMotionDetectClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstBaseTransformClass *gstbasetrans_class = GST_BASE_TRANSFORM_CLASS (klass);

  gobject_class->set_property = gst_motiondetect_set_property;
  gobject_class->get_property = gst_motiondetect_get_property;
  gobject_class->finalize = gst_motiondetect_finalize;

  g_object_class_install_property (gobject_class, PROP_ENABLED,
      g_param_spec_boolean ("enabled", "enabled",
          "Post a message when differences found between successive frames",
          FALSE,
          G_PARAM_READWRITE | G_PARAM_CONSTRUCT | G_PARAM_STATIC_STRINGS));

  GST_DEBUG_CATEGORY_INIT (
      gst_motiondetect_debug, "stbt-motiondetect", 0, "Motion detection");

  gstbasetrans_class->transform_ip =
      GST_DEBUG_FUNCPTR (gst_motiondetect_transform_ip);
  gstbasetrans_class->passthrough_on_same_caps = TRUE;
}

static void
gst_motiondetect_init (GstMotionDetect * filter, GstMotionDetectClass * gclass)
{
  filter->enabled = FALSE;
  gst_base_transform_set_gap_aware (GST_BASE_TRANSFORM_CAST (filter), TRUE);
}

static void
gst_motiondetect_finalize (GObject * object)
{
  G_OBJECT_CLASS (parent_class)->finalize (object);
}

static void
gst_motiondetect_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  GstMotionDetect *filter = GST_MOTIONDETECT (object);

  switch (prop_id) {
    case PROP_ENABLED:
      GST_OBJECT_LOCK (filter);
      filter->enabled = g_value_get_boolean (value);
      GST_OBJECT_UNLOCK (filter);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_motiondetect_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
  GstMotionDetect *filter = GST_MOTIONDETECT (object);

  switch (prop_id) {
    case PROP_ENABLED:
      g_value_set_boolean (value, filter->enabled);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static GstFlowReturn
gst_motiondetect_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstMotionDetect *filter = GST_MOTIONDETECT (trans);

  return GST_FLOW_OK;
}
