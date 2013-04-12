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
 * If the #StbtMotionDetect:enabled property is %TRUE, compares successive
 * video frames and sends a message named #motiondetect if it detects
 * differences between two frames.
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
#define DEFAULT_NOISE_THRESHOLD (0.84f)

enum
{
    LAST_SIGNAL
};

enum
{
    PROP_0,
    PROP_ENABLED,
    PROP_DEBUG_DIRECTORY,
    PROP_NOISE_THRESHOLD,
    PROP_MASK,
    PROP_DISPLAY,
};

GST_BOILERPLATE (StbtMotionDetect, gst_motiondetect, GstBaseTransform,
    GST_TYPE_BASE_TRANSFORM);

static void gst_motiondetect_finalize (GObject * object);
static void gst_motiondetect_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_motiondetect_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static gboolean gst_motiondetect_set_caps (GstBaseTransform * trans,
    GstCaps * incaps, GstCaps * outcaps);
    
static void gst_motiondetect_log_image (const IplImage * image,
    const char * debugDirectory, int index, const char * filename);
static GstFlowReturn gst_motiondetect_transform_ip (GstBaseTransform * trans,
    GstBuffer * buf);
static gboolean gst_motiondetect_apply (IplImage * cvReferenceImage,
    const IplImage * cvCurrentImage, const IplImage * cvMaskImage,
    float noiseThreshold);

static void gst_motiondetect_set_debug_directory (StbtMotionDetect * filter,
    char* debugDirectory);
static void gst_motiondetect_load_mask (StbtMotionDetect * filter,
    char * mask);
static gboolean gst_motiondetect_check_mask_compability (
    StbtMotionDetect * filter);

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
gst_motiondetect_class_init (StbtMotionDetectClass * klass)
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
  g_object_class_install_property (gobject_class, PROP_DEBUG_DIRECTORY,
      g_param_spec_string ("debugDirectory", "Debug directory",
          "Directory to store intermediate results for debugging the "
          "motiondetect algorithm",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_NOISE_THRESHOLD,
      g_param_spec_float ("noiseThreshold", "Noise threshold",
          "Specifies the threshold to use to confirm motion.",
          0.0f, 1.0f, DEFAULT_NOISE_THRESHOLD,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_MASK,
      g_param_spec_string ("mask", "Mask", "Filename of mask image",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_DISPLAY,
      g_param_spec_boolean ("display", "Display",
          "Sets whether detected motion should be highlighted in the output",
          TRUE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  GST_DEBUG_CATEGORY_INIT (
      gst_motiondetect_debug, "stbt-motiondetect", 0, "Motion detection");

  gstbasetrans_class->transform_ip =
      GST_DEBUG_FUNCPTR (gst_motiondetect_transform_ip);
  gstbasetrans_class->passthrough_on_same_caps = TRUE;
  gstbasetrans_class->set_caps = gst_motiondetect_set_caps;
}

static void
gst_motiondetect_init (StbtMotionDetect * filter,
    StbtMotionDetectClass * gclass)
{
  filter->enabled = FALSE;
  filter->state = MOTION_DETECT_STATE_INITIALISING;
  filter->cvCurrentImage = NULL;
  filter->cvReferenceImageGray = NULL;
  filter->cvCurrentImageGray = NULL;
  filter->cvMaskImage = NULL;
  filter->cvInvertedMaskImage = NULL;
  filter->mask = NULL;
  filter->debugDirectory = NULL;
  filter->noiseThreshold = DEFAULT_NOISE_THRESHOLD;
  filter->display = TRUE;

  gst_base_transform_set_gap_aware (GST_BASE_TRANSFORM_CAST (filter), TRUE);
}

static void
gst_motiondetect_finalize (GObject * object)
{
  G_OBJECT_CLASS (parent_class)->finalize (object);

  StbtMotionDetect *filter = GST_MOTIONDETECT (object);
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
  if (filter->cvInvertedMaskImage) {
    cvReleaseImage (&filter->cvInvertedMaskImage);
  }
  if (filter->mask) {
    g_free(filter->mask);
  }
  if (filter->debugDirectory) {
    g_free (filter->debugDirectory);
  }
}

static void
gst_motiondetect_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  StbtMotionDetect *filter = GST_MOTIONDETECT (object);

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
    case PROP_DEBUG_DIRECTORY:
      gst_motiondetect_set_debug_directory (
          filter, g_value_dup_string (value));
      break;
    case PROP_NOISE_THRESHOLD:
      GST_OBJECT_LOCK(filter);
      filter->noiseThreshold = g_value_get_float (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_MASK:
      gst_motiondetect_load_mask (filter, g_value_dup_string (value));
      break;
    case PROP_DISPLAY:
      GST_OBJECT_LOCK(filter);
      filter->display = g_value_get_boolean (value);
      GST_OBJECT_UNLOCK(filter);
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
  StbtMotionDetect *filter = GST_MOTIONDETECT (object);

  switch (prop_id) {
    case PROP_ENABLED:
      g_value_set_boolean (value, filter->enabled);
      break;
    case PROP_DEBUG_DIRECTORY:
      g_value_set_string (value, filter->debugDirectory);
      break;
    case PROP_NOISE_THRESHOLD:
      g_value_set_float (value, filter->noiseThreshold);
      break;
    case PROP_MASK:
      g_value_set_string (value, filter->mask);
      break;
    case PROP_DISPLAY:
      g_value_set_boolean (value, filter->display);
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
  gint width, height, depth, ipldepth, channels;
  GError *err = NULL;
  GstStructure *structure = gst_caps_get_structure (incaps, 0);
  StbtMotionDetect *filter = GST_MOTIONDETECT (trans);
  if (!filter) {
    return FALSE;
  }
  
  if (!gst_structure_get_int (structure, "width", &width) ||
      !gst_structure_get_int (structure, "height", &height) ||
      !gst_structure_get_int (structure, "depth", &depth)) {
    g_set_error (&err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "No width/height/depth in caps");
    return FALSE;
  }
  if (gst_structure_has_name (structure, "video/x-raw-rgb")) {
    channels = 3;
  } else if (gst_structure_has_name (structure, "video/x-raw-gray")) {
    channels = 1;
  } else {
    g_set_error (&err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "Unsupported caps %s", gst_structure_get_name (structure));
    return FALSE;
  }
  if (depth / channels == 8) {
    ipldepth = IPL_DEPTH_8U;
  } else {
    g_set_error (&err, GST_CORE_ERROR, GST_CORE_ERROR_NEGOTIATION,
        "Unsupported depth/channels %d/%d", depth, channels);
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
    cvCreateImageHeader (cvSize (width, height), ipldepth, channels);
  filter->cvReferenceImageGray = cvCreateImage(
    cvSize (width, height), IPL_DEPTH_8U, 1);
  filter->cvCurrentImageGray = cvCreateImage(
    cvSize (width, height), IPL_DEPTH_8U, 1);

  filter->state = MOTION_DETECT_STATE_ACQUIRING_REFERENCE_IMAGE;

  return gst_motiondetect_check_mask_compability(filter);
}

static void
gst_motiondetect_log_image (const IplImage * image,
    const char * debugDirectory, int index, const char * filename)
{
  if (image && debugDirectory) {
    char *filepath;
    asprintf (&filepath, "%s/%05d_%s", debugDirectory, index, filename);

    if (image->depth == IPL_DEPTH_32F) {
      IplImage *scaledImageToLog = cvCreateImage (
          cvSize (image->width, image->height), IPL_DEPTH_8U, 1);
      cvConvertScale (image, scaledImageToLog, 255.0, 0);
      cvSaveImage (filepath, scaledImageToLog, NULL);
      cvReleaseImage (&scaledImageToLog);
    } else {
      cvSaveImage (filepath, image, NULL);
    }

    free (filepath);
  }
}

static GstFlowReturn
gst_motiondetect_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstMessage *m = NULL;
  StbtMotionDetect *filter = GST_MOTIONDETECT (trans);
  if ((!filter) || (!buf)) {
    return GST_FLOW_OK;
  }

  GST_OBJECT_LOCK(filter);
  if (filter->enabled && filter->state != MOTION_DETECT_STATE_INITIALISING) {
    IplImage *referenceImageGrayTmp = NULL;
    static int frameNo = 1;

    filter->cvCurrentImage->imageData = (char *) GST_BUFFER_DATA (buf);
    cvCvtColor( filter->cvCurrentImage,
        filter->cvCurrentImageGray, CV_BGR2GRAY );

    if (filter->debugDirectory) {
      gst_motiondetect_log_image (filter->cvCurrentImageGray, 
          filter->debugDirectory, frameNo, "source.png");
    }

    if (filter->state == MOTION_DETECT_STATE_REFERENCE_IMAGE_ACQUIRED) {
      gboolean result;
      
      result = gst_motiondetect_apply(
          filter->cvReferenceImageGray, filter->cvCurrentImageGray,
          filter->cvMaskImage, filter->noiseThreshold);

      if (filter->debugDirectory) {
        if (result) {
          gst_motiondetect_log_image (filter->cvReferenceImageGray, 
              filter->debugDirectory, frameNo,
              "absdiff_not_masked_motion.png");
        } else {
          gst_motiondetect_log_image (filter->cvReferenceImageGray, 
              filter->debugDirectory, frameNo,
              "absdiff_not_masked_no_motion.png");
        }
        gst_motiondetect_log_image (filter->cvMaskImage,
              filter->debugDirectory, frameNo, "mask.png");
      }

      guint64 timestamp = GST_BUFFER_TIMESTAMP(buf);
      GstStructure *s = gst_structure_new ("motiondetect",
          "has_motion", G_TYPE_BOOLEAN, result,
          "timestamp", G_TYPE_UINT64, timestamp,
          "masked", G_TYPE_BOOLEAN, (filter->mask != NULL),
          "mask_path", G_TYPE_STRING, filter->mask, NULL);
      m = gst_message_new_element (GST_OBJECT (filter), s);

      if (filter->display) {
        buf = gst_buffer_make_writable (buf);
        cvSubS (filter->cvCurrentImage, CV_RGB(100, 100, 100),
            filter->cvCurrentImage, filter->cvInvertedMaskImage);
        if (result) {
          cvAddS (filter->cvCurrentImage, CV_RGB(50, 0, 0),
              filter->cvCurrentImage, filter->cvMaskImage);
        }
      }
    }

    referenceImageGrayTmp = filter->cvReferenceImageGray;
    filter->cvReferenceImageGray = filter->cvCurrentImageGray;
    filter->cvCurrentImageGray = referenceImageGrayTmp;
    filter->state = MOTION_DETECT_STATE_REFERENCE_IMAGE_ACQUIRED;
    ++frameNo;
  }
  GST_OBJECT_UNLOCK(filter);

  if (m) {
    gst_element_post_message (GST_ELEMENT (filter), m);
  }

  return GST_FLOW_OK;
}

static gboolean gst_motiondetect_apply (
    IplImage * cvReferenceImage, const IplImage * cvCurrentImage,
    const IplImage * cvMaskImage, float noiseThreshold)
{
  IplConvKernel *kernel = cvCreateStructuringElementEx (3, 3, 1, 1,
      CV_SHAPE_ELLIPSE, NULL);
  int threshold = (int)((1 - noiseThreshold) * 255);
  IplImage *cvAbsDiffImage = cvReferenceImage;
  double maxVal = -1.0;

  cvAbsDiff( cvReferenceImage, cvCurrentImage, cvAbsDiffImage );
  cvThreshold (cvAbsDiffImage, cvAbsDiffImage, threshold, 255,
      CV_THRESH_BINARY);
  cvErode (cvAbsDiffImage, cvAbsDiffImage, kernel, 1);

  cvReleaseStructuringElement(&kernel);

  cvMinMaxLoc(cvAbsDiffImage, NULL, &maxVal, NULL, NULL, cvMaskImage );
  if (maxVal > 0) {
    return TRUE;
  } else {
    return FALSE;
  }

}

/* We take ownership of debugDirectory here */
static void
gst_motiondetect_set_debug_directory (
    StbtMotionDetect * filter, char* debugDirectory)
{
  GST_OBJECT_LOCK (filter);
  if (filter->debugDirectory) {
    g_free (filter->debugDirectory);
  }
  filter->debugDirectory = debugDirectory;
  GST_OBJECT_UNLOCK (filter);
}

/* We take ownership of mask here */
static void
gst_motiondetect_load_mask (StbtMotionDetect * filter, char* mask)
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
      g_free (mask);
      mask = NULL;
    }
    gst_motiondetect_check_mask_compability(filter);
  }

  GST_OBJECT_LOCK(filter);
  oldMaskFilename = filter->mask;
  filter->mask = mask;
  oldMaskImage = filter->cvMaskImage;
  filter->cvMaskImage = newMaskImage;

  if (filter->cvInvertedMaskImage) {
    cvReleaseImage (&filter->cvInvertedMaskImage);
    filter->cvInvertedMaskImage = NULL;
  }
  if (filter->cvMaskImage) {
    filter->cvInvertedMaskImage = cvCloneImage (filter->cvMaskImage);
    cvNot(filter->cvMaskImage, filter->cvInvertedMaskImage);
  }
  GST_OBJECT_UNLOCK(filter);

  cvReleaseImage (&oldMaskImage);
  g_free(oldMaskFilename);
}


static gboolean
gst_motiondetect_check_mask_compability (StbtMotionDetect *filter)
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
