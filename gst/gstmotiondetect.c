/* Gstreamer element for motion detection (not motion tracking) using OpenCV.
 *
 * Copyright (C) 2012 YouView TV Ltd.
 * Author: Hubert Lacote <hubert.lacote@gmail.com>
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
    PROP_MASK,
};

GST_BOILERPLATE (GstMotionDetect, gst_motiondetect, GstBaseTransform,
    GST_TYPE_BASE_TRANSFORM);

static void gst_motiondetect_finalize (GObject * object);
static void gst_motiondetect_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_motiondetect_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static gboolean gst_motiondetect_set_caps (GstBaseTransform * trans,
    GstCaps * incaps, GstCaps * outcaps);
static GstFlowReturn gst_motiondetect_transform_ip (GstBaseTransform * trans,
    GstBuffer * buf);
static gboolean gst_motiondetect_apply (IplImage * cvReferenceImage,
    const IplImage * cvCurrentImage, const IplImage * cvMaskImage);
static void gst_motiondetect_load_mask (GstMotionDetect * filter, char * mask);
static gboolean gst_motiondetect_check_mask_compability (
    GstMotionDetect * filter);

static gboolean
gst_opencv_get_ipl_depth_and_channels (GstStructure * structure,
    gint * ipldepth, gint * channels, GError ** err)
{
  gint depth, bpp;

  if (!gst_structure_get_int (structure, "depth", &depth) ||
      !gst_structure_get_int (structure, "bpp", &bpp)) {
    g_set_error (err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "No depth/bpp in caps");
    return FALSE;
  }

  if (depth != bpp) {
    g_set_error (err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "Depth and bpp should be equal");
    return FALSE;
  }

  if (gst_structure_has_name (structure, "video/x-raw-rgb")) {
    *channels = 3;
  } else if (gst_structure_has_name (structure, "video/x-raw-gray")) {
    *channels = 1;
  } else {
    g_set_error (err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "Unsupported caps %s", gst_structure_get_name (structure));
    return FALSE;
  }

  if (depth / *channels == 8) {
    /* TODO signdness? */
    *ipldepth = IPL_DEPTH_8U;
  } else if (depth / *channels == 16) {
    *ipldepth = IPL_DEPTH_16U;
  } else {
    g_set_error (err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "Unsupported depth/channels %d/%d", depth, *channels);
    return FALSE;
  }

  return TRUE;
}

gboolean
gst_opencv_parse_iplimage_params_from_structure (GstStructure * structure,
    gint * width, gint * height, gint * ipldepth, gint * channels,
    GError ** err)
{
  if (!gst_opencv_get_ipl_depth_and_channels (structure, ipldepth, channels,
          err)) {
    return FALSE;
  }

  if (!gst_structure_get_int (structure, "width", width) ||
      !gst_structure_get_int (structure, "height", height)) {
    g_set_error (err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "No width/height in caps");
    return FALSE;
  }

  return TRUE;
}

gboolean
gst_opencv_parse_iplimage_params_from_caps (GstCaps * caps, gint * width,
    gint * height, gint * ipldepth, gint * channels, GError ** err)
{
  return
      gst_opencv_parse_iplimage_params_from_structure (gst_caps_get_structure
      (caps, 0), width, height, ipldepth, channels, err);
}


static void
gst_motiondetect_base_init (gpointer gclass)
{
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (gclass);

  gst_element_class_set_details_simple (gstelement_class,
      "Motion detection",
      "Filter/Analyzer/Video",
      "Reports if any differences were found between successive frames",
      "Hubert Lacote <hubert.lacote@gmail.com>");
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

  g_object_class_install_property (gobject_class, PROP_MASK,
      g_param_spec_string ("mask", "Mask", "Filename of mask image",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  GST_DEBUG_CATEGORY_INIT (
      gst_motiondetect_debug, "stbt-motiondetect", 0, "Motion detection");

  gstbasetrans_class->transform_ip =
      GST_DEBUG_FUNCPTR (gst_motiondetect_transform_ip);
  gstbasetrans_class->passthrough_on_same_caps = TRUE;
  gstbasetrans_class->set_caps = gst_motiondetect_set_caps;
}

static void
gst_motiondetect_init (GstMotionDetect * filter, GstMotionDetectClass * gclass)
{
  filter->enabled = FALSE;
  filter->state = MOTION_DETECT_STATE_INITIALISING;
  filter->cvCurrentImage = NULL;
  filter->cvReferenceImageGray = NULL;
  filter->cvCurrentImageGray = NULL;
  filter->cvMaskImage = NULL;
  filter->mask = NULL;

  gst_base_transform_set_gap_aware (GST_BASE_TRANSFORM_CAST (filter), TRUE);
}

static void
gst_motiondetect_finalize (GObject * object)
{
  G_OBJECT_CLASS (parent_class)->finalize (object);

  GstMotionDetect *filter = GST_MOTIONDETECT (object);
  if (filter->cvCurrentImage) {
    cvReleaseImageHeader (&filter->cvCurrentImage);
  }
  if (filter->cvReferenceImageGray) {
    cvReleaseImage (&filter->cvReferenceImageGray);
  }
  if (filter->cvCurrentImageGray) {
    cvReleaseImage (&filter->cvCurrentImageGray);
  }
  if (filter->cvMaskImage) {
    cvReleaseImage (&filter->cvMaskImage);
  }
  if (filter->mask) {
    g_free(filter->mask);
  }
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
      if (filter->enabled) {
        // "Drop" the reference image
        filter->state = MOTION_DETECT_STATE_ACQUIRING_REFERENCE_IMAGE;
      }
      GST_OBJECT_UNLOCK (filter);
      break;
    case PROP_MASK:
      gst_motiondetect_load_mask (filter, g_value_dup_string (value));
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
    case PROP_MASK:
      g_value_set_string (value, filter->mask);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static gboolean
gst_motiondetect_set_caps (GstBaseTransform *trans, GstCaps *incaps,
    GstCaps *outcaps)
{
  gint in_width, in_height;
  gint in_depth, in_channels;
  GError *in_err = NULL;
  GstMotionDetect *filter = GST_MOTIONDETECT (trans);
  if (!filter) {
    return FALSE;
  }

  if (!gst_opencv_parse_iplimage_params_from_caps (incaps, &in_width,
          &in_height, &in_depth, &in_channels, &in_err)) {
    GST_WARNING_OBJECT (trans, "Failed to parse input caps: %s",
        in_err->message);
    g_error_free (in_err);
    return FALSE;
  }

  if (filter->cvCurrentImage) {
    cvReleaseImageHeader (&filter->cvCurrentImage);
    filter->cvCurrentImage = NULL;
  }
  if (filter->cvReferenceImageGray) {
    cvReleaseImage (&filter->cvReferenceImageGray);
    filter->cvReferenceImageGray = NULL;
  }
  if (filter->cvCurrentImageGray) {
    cvReleaseImage (&filter->cvCurrentImageGray);
    filter->cvCurrentImageGray = NULL;
  }

  filter->cvCurrentImage =
    cvCreateImageHeader (cvSize (in_width, in_height), in_depth, in_channels);
  filter->cvReferenceImageGray = cvCreateImage(
    cvSize (in_width, in_height), IPL_DEPTH_8U, 1);
  filter->cvCurrentImageGray = cvCreateImage(
    cvSize (in_width, in_height), IPL_DEPTH_8U, 1);

  filter->state = MOTION_DETECT_STATE_ACQUIRING_REFERENCE_IMAGE;

  return gst_motiondetect_check_mask_compability(filter);
}

static GstFlowReturn
gst_motiondetect_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstMessage *m = NULL;
  GstMotionDetect *filter = GST_MOTIONDETECT (trans);
  if ((!filter) || (!buf)) {
    return GST_FLOW_OK;
  }

  GST_OBJECT_LOCK(filter);
  if (filter->enabled && filter->state != MOTION_DETECT_STATE_INITIALISING) {
    IplImage *referenceImageGrayTmp = NULL;

    filter->cvCurrentImage->imageData = (char *) GST_BUFFER_DATA (buf);
    cvCvtColor( filter->cvCurrentImage,
        filter->cvCurrentImageGray, CV_BGR2GRAY );

    if (filter->state == MOTION_DETECT_STATE_REFERENCE_IMAGE_ACQUIRED) {
      gboolean result;
      result = gst_motiondetect_apply(
          filter->cvReferenceImageGray, filter->cvCurrentImageGray,
          filter->cvMaskImage );
      GstStructure *s = gst_structure_new ("motiondetect",
          "has_motion", G_TYPE_BOOLEAN, result, NULL);
      m = gst_message_new_element (GST_OBJECT (filter), s);
    }

    referenceImageGrayTmp = filter->cvReferenceImageGray;
    filter->cvReferenceImageGray = filter->cvCurrentImageGray;
    filter->cvCurrentImageGray = referenceImageGrayTmp;
    filter->state = MOTION_DETECT_STATE_REFERENCE_IMAGE_ACQUIRED;
  }
  GST_OBJECT_UNLOCK(filter);

  if (m) {
    gst_element_post_message (GST_ELEMENT (filter), m);
  }

  return GST_FLOW_OK;
}

static gboolean gst_motiondetect_apply (
    IplImage * cvReferenceImage, const IplImage * cvCurrentImage,
    const IplImage * cvMaskImage)
{

  IplImage *cvAbsDiffImage = cvReferenceImage;
  double maxVal = -1.0;

  cvAbsDiff( cvReferenceImage, cvCurrentImage, cvAbsDiffImage );

  cvMinMaxLoc(cvAbsDiffImage, NULL, &maxVal, NULL, NULL, cvMaskImage );
  if (maxVal > 40 ) {
    return TRUE;
  } else {
    return FALSE;
  }

}

/* We take ownership of mask here */
static void
gst_motiondetect_load_mask (GstMotionDetect * filter, char* mask)
{
  char *oldMaskFilename = NULL;
  IplImage *oldMaskImage = NULL, *newMaskImage = NULL;

  if (mask) {
    newMaskImage = cvLoadImage (mask, CV_LOAD_IMAGE_GRAYSCALE);
    if (!newMaskImage) {
      /* Unfortunately OpenCV doesn't seem to provide any way of finding out
         why the image load failed, so we can't be more specific than FAILED: */
      GST_ELEMENT_WARNING (filter, RESOURCE, FAILED,
          ("OpenCV failed to load mask image"),
          ("While attempting to load mask '%s'", mask));
      GST_WARNING ("Couldn't load mask image: %s. error: %s",
          mask, g_strerror (errno));
    }
    gst_motiondetect_check_mask_compability(filter);
    g_free (mask);
    mask = NULL;
  }

  GST_OBJECT_LOCK(filter);
  oldMaskFilename = filter->mask;
  filter->mask = mask;
  oldMaskImage = filter->cvMaskImage;
  filter->cvMaskImage = newMaskImage;
  GST_OBJECT_UNLOCK(filter);

  cvReleaseImage (&oldMaskImage);
  g_free(oldMaskFilename);
}


static gboolean
gst_motiondetect_check_mask_compability (GstMotionDetect *filter)
{
  if (filter->state != MOTION_DETECT_STATE_INITIALISING &&
      filter->cvMaskImage != NULL &&
      (filter->cvMaskImage->width != filter->cvCurrentImage->width ||
       filter->cvMaskImage->height != filter->cvCurrentImage->height)) {
    GST_WARNING_OBJECT (filter, "The dimensions of the mask '%s' don't match \
                                the input caps: %d %d != %d %d",
                                filter->mask,
                                filter->cvMaskImage->width,
                                filter->cvMaskImage->height,
                                filter->cvCurrentImage->width,
                                filter->cvCurrentImage->height);
    return FALSE;
  } else {
    return TRUE;
  }
}
