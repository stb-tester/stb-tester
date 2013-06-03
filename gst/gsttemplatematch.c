/*
 * GStreamer
 * Copyright (C) 2005 Thomas Vander Stichele <thomas@apestaart.org>
 * Copyright (C) 2005 Ronald S. Bultje <rbultje@ronald.bitfreak.net>
 * Copyright (C) 2008 Michael Sheldon <mike@mikeasoft.com>
 * Copyright (C) 2009 Noam Lewis <jones.noamle@gmail.com>
 * Copyright (C) 2012 YouView TV Ltd.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 *
 * Alternatively, the contents of this file may be used under the
 * GNU Lesser General Public License Version 2.1 (the "LGPL"), in
 * which case the following provisions apply instead of the ones
 * mentioned above:
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Library General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Library General Public License for more details.
 *
 * You should have received a copy of the GNU Library General Public
 * License along with this library; if not, write to the
 * Free Software Foundation, Inc., 59 Temple Place - Suite 330,
 * Boston, MA 02111-1307, USA.
 */

/**
 * SECTION:element-templatematch
 *
 * If the image specified by the path in property #StbtTemplateMatch:template
 * is successfully read, searches for that image in each frame of video and
 * sends a message named #template_match with the following fields:
 *
 * - #guint #template_match.x: The x coordinate of the match
 * - #guint #template_match.y: The y coordinate of the match
 * - #string #template_match.template_path: The value of the
 *     #StbtTemplateMatch:template file matched.
 * - #gboolean #template_match.match: Whether or not a match was found
 *     (when %FALSE, the fields #template_match.x and #template_match.y
 *     contain the coordinates of the best --but not good enough-- match).
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch-0.10 videotestsrc ! decodebin ! ffmpegcolorspace ! templatematch template=/path/to/file.jpg ! ffmpegcolorspace ! xvimagesink
 * ]|
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#  include <config.h>
#endif

#include <gst/gst.h>
#include <gst/video/video.h>
#include <math.h>

#include "gsttemplatematch.h"

GST_DEBUG_CATEGORY_STATIC (gst_templatematch_debug);
#define GST_CAT_DEFAULT gst_templatematch_debug

#define DEFAULT_MATCH_METHOD GST_TM_MATCH_METHOD_CV_TM_SQDIFF_NORMED
#define DEFAULT_MATCH_THRESHOLD (0.80f)
#define DEFAULT_CONFIRM_METHOD GST_TM_CONFIRM_METHOD_ABSDIFF
#define DEFAULT_ERODE_PASSES (1)
#define DEFAULT_CONFIRM_THRESHOLD (0.16f)


#define GST_TM_MATCH_METHOD (gst_tm_match_method_get_type())
static GType
gst_tm_match_method_get_type (void)
{
  static GType gst_tm_match_method_type = 0;
  static const GEnumValue match_method_types[] = {
    {GST_TM_MATCH_METHOD_CV_TM_SQDIFF_NORMED, "CV_TM_SQDIFF_NORMED",
        "sqdiff-normed"},
    {GST_TM_MATCH_METHOD_CV_TM_CCORR_NORMED, "CV_TM_CCORR_NORMED",
        "ccorr-normed"},
    {GST_TM_MATCH_METHOD_CV_TM_CCOEFF_NORMED, "CV_TM_CCOEFF_NORMED",
        "ccoeff-normed"},
    {0, NULL, NULL}
  };
  if (!gst_tm_match_method_type) {
    gst_tm_match_method_type =
        g_enum_register_static ("GstTMMatchMethod", match_method_types);
  }
  return gst_tm_match_method_type;
}

#define GST_TM_SINGLE_FRAME (gst_tm_single_frame_get_type())
static GType
gst_tm_single_frame_get_type (void)
{
  static GType gst_tm_single_frame_type = 0;
  static const GEnumValue single_frame_types[] = {
    {GST_TM_SINGLE_FRAME_DISABLED, "Do not operate in frame-by-frame mode",
        "disabled"},
    {GST_TM_SINGLE_FRAME_NEXT, "Request the next frame",
        "next"},
    {GST_TM_SINGLE_FRAME_WAIT, "Wait until the next request is made",
        "wait"},
    {0, NULL, NULL}
  };
  if (!gst_tm_single_frame_type) {
	  gst_tm_single_frame_type =
        g_enum_register_static ("GstTMSingleFrameMode", single_frame_types);
  }
  return gst_tm_single_frame_type;
}

#define GST_TM_CONFIRM_METHOD (gst_tm_confirm_method_get_type())
static GType
gst_tm_confirm_method_get_type (void)
{
  static GType gst_tm_confirm_method_type = 0;
  static const GEnumValue confirm_method_types[] = {
    {GST_TM_CONFIRM_METHOD_NONE, "Do not use confirm step", "none"},
    {GST_TM_CONFIRM_METHOD_ABSDIFF, "Absolute difference", "absdiff"},
    {GST_TM_CONFIRM_METHOD_NORMED_ABSDIFF, "Normalised absolute difference",
        "normed-absdiff"},
    {0, NULL, NULL}
  };
  if (!gst_tm_confirm_method_type) {
    gst_tm_confirm_method_type =
        g_enum_register_static ("GstTMConfirmMethod", confirm_method_types);
  }
  return gst_tm_confirm_method_type;
}

/* Filter signals and args */
enum
{
  /* FILL ME */
  LAST_SIGNAL
};

enum
{
  PROP_0,
  PROP_MATCH_METHOD,
  PROP_MATCH_THRESHOLD,
  PROP_CONFIRM_METHOD,
  PROP_ERODE_PASSES,
  PROP_CONFIRM_THRESHOLD,
  PROP_TEMPLATE,
  PROP_DEBUG_DIRECTORY,
  PROP_DISPLAY,
  PROP_SINGLE_FRAME,
};

/* the capabilities of the inputs and outputs.
 */
static GstStaticPadTemplate sink_factory = GST_STATIC_PAD_TEMPLATE ("sink",
    GST_PAD_SINK,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_BGR)
    );

static GstStaticPadTemplate src_factory = GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_BGR)
    );

GST_BOILERPLATE (StbtTemplateMatch, gst_templatematch, GstElement,
    GST_TYPE_ELEMENT);

static void gst_templatematch_finalize (GObject * object);
static void gst_templatematch_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_templatematch_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);

static gboolean gst_templatematch_set_caps (GstPad * pad, GstCaps * caps);
static GstFlowReturn gst_templatematch_chain (GstPad * pad, GstBuffer * buf);

static void gst_templatematch_log_image (const IplImage * image,
    const char * debugDirectory, const char * filename);
static void gst_templatematch_set_debug_directory (StbtTemplateMatch * filter,
    char* debugDirectory);

static void gst_templatematch_load_template (
    StbtTemplateMatch * filter, char * template);
static void gst_templatematch_match (IplImage * input, IplImage * template,
    IplImage * dist_image, double *best_res, CvPoint * best_pos, int method);

/* gst_templatematch_confirm methods */
static gboolean gst_templatematch_confirm (IplImage * inputROIGray,
    IplImage * input, const IplImage * templateGray, float confirmThreshold,
    const CvPoint * bestPos, const int method, const int erodePasses,
    const char * debugDirectory);
static gboolean gst_templatematch_confirm_absdiff (IplImage * inputROIGray,
    IplImage * input, const IplImage * templateGray, float confirmThreshold,
    const CvPoint * bestPos, const int erodePasses,
    const char * debugDirectory);
static gboolean gst_templatematch_confirm_normed_absdiff (IplImage * inputROIGray,
    IplImage * input, const IplImage * templateGray, float confirmThreshold,
    const CvPoint * bestPos, const int erodePasses,
    const char * debugDirectory);

static void gst_templatematch_rebuild_dist_image (StbtTemplateMatch * filter);
static void gst_templatematch_rebuild_template_images (
    StbtTemplateMatch * filter);

/* GObject vmethod implementations */

static void
gst_templatematch_base_init (gpointer gclass)
{
  GstElementClass *element_class = GST_ELEMENT_CLASS (gclass);

  gst_element_class_set_details_simple (element_class,
      "templatematch",
      "Filter/Effect/Video",
      "Performs template matching on videos and images, providing detected positions via bus messages",
      "Noam Lewis <jones.noamle@gmail.com>");

  gst_element_class_add_pad_template (element_class,
      gst_static_pad_template_get (&src_factory));
  gst_element_class_add_pad_template (element_class,
      gst_static_pad_template_get (&sink_factory));
}

/* initialize the templatematch's class */
static void
gst_templatematch_class_init (StbtTemplateMatchClass * klass)
{
  GObjectClass *gobject_class;

  gobject_class = (GObjectClass *) klass;

  gobject_class->finalize = gst_templatematch_finalize;
  gobject_class->set_property = gst_templatematch_set_property;
  gobject_class->get_property = gst_templatematch_get_property;

  g_object_class_install_property (gobject_class, PROP_MATCH_METHOD,
      g_param_spec_enum ("matchMethod", "Match method",
          "The algorithm for finding the template within the video frame. "
          "For details see http://docs.opencv.org/modules/imgproc/doc/"
          "object_detection.html#matchtemplate",
          GST_TM_MATCH_METHOD, DEFAULT_MATCH_METHOD,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_MATCH_THRESHOLD,
      g_param_spec_float ("matchThreshold", "Match threshold",
          "Threshold to use to find a potential match",
          0.0f, 1.0f, DEFAULT_MATCH_THRESHOLD,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_CONFIRM_METHOD,
      g_param_spec_enum ("confirmMethod", "Match confirm method",
          "Algorithm to confirm the match found by \"matchMethod\"",
          GST_TM_CONFIRM_METHOD, DEFAULT_CONFIRM_METHOD,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_ERODE_PASSES,
      g_param_spec_int ("erodePasses", "Erode passes",
          "Number of times to apply the erode step in the confirm algorithm",
          0, 10, DEFAULT_ERODE_PASSES,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_CONFIRM_THRESHOLD,
      g_param_spec_float ("confirmThreshold", "Confirm threshold",
          "Threshold to use in the confirm algorithm",
          0.0f, 1.0f, DEFAULT_CONFIRM_THRESHOLD,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_TEMPLATE,
      g_param_spec_string ("template", "Template", "Filename of template image",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_DEBUG_DIRECTORY,
      g_param_spec_string ("debugDirectory", "Debug directory",
          "Directory to store intermediate results for debugging the "
          "templatematch algorithm",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_DISPLAY,
      g_param_spec_boolean ("display", "Display",
          "Highlight the detected template in the output",
          TRUE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
  g_object_class_install_property (gobject_class, PROP_SINGLE_FRAME,
        g_param_spec_enum ("singleFrameMode", "Single frame mode",
            "Frame-by-frame operation mode",
            GST_TM_SINGLE_FRAME, 0,
            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
}

/* initialize the new element
 * instantiate pads and add them to element
 * set pad callback functions
 * initialize instance structure
 */
static void
gst_templatematch_init (StbtTemplateMatch * filter,
    StbtTemplateMatchClass * gclass)
{
  filter->sinkpad = gst_pad_new_from_static_template (&sink_factory, "sink");
  gst_pad_set_setcaps_function (filter->sinkpad,
      GST_DEBUG_FUNCPTR (gst_templatematch_set_caps));
  gst_pad_set_getcaps_function (filter->sinkpad,
      GST_DEBUG_FUNCPTR (gst_pad_proxy_getcaps));
  gst_pad_set_chain_function (filter->sinkpad,
      GST_DEBUG_FUNCPTR (gst_templatematch_chain));

  filter->srcpad = gst_pad_new_from_static_template (&src_factory, "src");
  gst_pad_set_getcaps_function (filter->srcpad,
      GST_DEBUG_FUNCPTR (gst_pad_proxy_getcaps));

  gst_element_add_pad (GST_ELEMENT (filter), filter->sinkpad);
  gst_element_add_pad (GST_ELEMENT (filter), filter->srcpad);
  filter->template = NULL;
  filter->display = TRUE;
  filter->cvTemplateImage = NULL;
  filter->cvDistImage = NULL;
  filter->cvImage = NULL;
  filter->cvImageROIGray = NULL;
  filter->cvTemplateImageGray = NULL;
  filter->matchMethod = DEFAULT_MATCH_METHOD;
  filter->matchThreshold = DEFAULT_MATCH_THRESHOLD;
  filter->confirmMethod = DEFAULT_CONFIRM_METHOD;
  filter->erodePasses = DEFAULT_ERODE_PASSES;
  filter->confirmThreshold = DEFAULT_CONFIRM_THRESHOLD;
  filter->singleFrameMode = GST_TM_SINGLE_FRAME_DISABLED;
  filter->debugDirectory = NULL;

  filter->templateImageAcquired = FALSE;
  filter->capsInitialised = FALSE;
}

static void
gst_templatematch_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  StbtTemplateMatch *filter = GST_TEMPLATEMATCH (object);

  switch (prop_id) {
    case PROP_MATCH_METHOD:
      GST_OBJECT_LOCK(filter);
      switch (g_value_get_enum (value)) {
        case GST_TM_MATCH_METHOD_CV_TM_SQDIFF_NORMED:
          filter->matchMethod = CV_TM_SQDIFF_NORMED;
          break;
        case GST_TM_MATCH_METHOD_CV_TM_CCORR_NORMED:
          filter->matchMethod = CV_TM_CCORR_NORMED;
          break;
        case GST_TM_MATCH_METHOD_CV_TM_CCOEFF_NORMED:
          filter->matchMethod = CV_TM_CCOEFF_NORMED;
          break;
      }
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_MATCH_THRESHOLD:
      GST_OBJECT_LOCK(filter);
      filter->matchThreshold = g_value_get_float (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_CONFIRM_METHOD:
      GST_OBJECT_LOCK(filter);
      filter->confirmMethod = g_value_get_enum (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_ERODE_PASSES:
      GST_OBJECT_LOCK(filter);
      filter->erodePasses = g_value_get_int (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_CONFIRM_THRESHOLD:
      GST_OBJECT_LOCK(filter);
      filter->confirmThreshold = g_value_get_float (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_DEBUG_DIRECTORY:
      gst_templatematch_set_debug_directory (
          filter, g_value_dup_string (value));
      break;
    case PROP_TEMPLATE:
      gst_templatematch_load_template (filter, g_value_dup_string (value));
      break;
    case PROP_DISPLAY:
      GST_OBJECT_LOCK(filter);
      filter->display = g_value_get_boolean (value);
      GST_OBJECT_UNLOCK(filter);
      break;
    case PROP_SINGLE_FRAME:
      GST_OBJECT_LOCK(filter);
      filter->singleFrameMode = g_value_get_enum (value);
      filter->singleFrameData = &filter->singleFrameMode;
      g_cond_signal (&filter->singleFrameModeModified);
      GST_OBJECT_UNLOCK(filter);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_templatematch_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
  StbtTemplateMatch *filter = GST_TEMPLATEMATCH (object);

  switch (prop_id) {
    case PROP_MATCH_METHOD:
      g_value_set_enum (value, filter->matchMethod);
      break;
    case PROP_MATCH_THRESHOLD:
      g_value_set_float (value, filter->matchThreshold);
      break;
    case PROP_CONFIRM_METHOD:
      g_value_set_enum (value, filter->confirmMethod);
      break;
    case PROP_ERODE_PASSES:
      g_value_set_int (value, filter->erodePasses);
      break;
    case PROP_CONFIRM_THRESHOLD:
      g_value_set_float (value, filter->confirmThreshold);
      break;
    case PROP_TEMPLATE:
      g_value_set_string (value, filter->template);
      break;
    case PROP_DEBUG_DIRECTORY:
      g_value_set_string (value, filter->debugDirectory);
      break;
    case PROP_DISPLAY:
      g_value_set_boolean (value, filter->display);
      break;
    case PROP_SINGLE_FRAME:
      g_value_set_enum (value, filter->singleFrameMode);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

/* GstElement vmethod implementations */

/* this function handles the link with other elements */
static gboolean
gst_templatematch_set_caps (GstPad * pad, GstCaps * caps)
{
  StbtTemplateMatch *filter;
  GstPad *otherpad;
  gint width, height;
  GstStructure *structure;

  filter = GST_TEMPLATEMATCH (gst_pad_get_parent (pad));
  structure = gst_caps_get_structure (caps, 0);
  gst_structure_get_int (structure, "width", &width);
  gst_structure_get_int (structure, "height", &height);

  if (filter->cvImage) {
    cvReleaseImageHeader (&filter->cvImage);
    filter->cvImage = NULL;
  }
  filter->cvImage =
      cvCreateImageHeader (cvSize (width, height), IPL_DEPTH_8U, 3);
  gst_templatematch_rebuild_dist_image (filter);

  filter->capsInitialised = (filter->cvImage != NULL);

  otherpad = (pad == filter->srcpad) ? filter->sinkpad : filter->srcpad;
  gst_object_unref (filter);

  return gst_pad_set_caps (otherpad, caps);
}

static void
gst_templatematch_finalize (GObject * object)
{
  StbtTemplateMatch *filter;
  filter = GST_TEMPLATEMATCH (object);

  g_free(filter->template);
  if (filter->debugDirectory) {
    g_free (filter->debugDirectory);
  }
  if (filter->cvImage) {
    cvReleaseImageHeader (&filter->cvImage);
  }
  if (filter->cvDistImage) {
    cvReleaseImage (&filter->cvDistImage);
  }
  if (filter->cvTemplateImage) {
    cvReleaseImage (&filter->cvTemplateImage);
  }
  if (filter->cvImageROIGray) {
    cvReleaseImage (&filter->cvImageROIGray);
  }
  if (filter->cvTemplateImageGray) {
    cvReleaseImage (&filter->cvTemplateImageGray);
  }
}

/* chain function
 * this function does the actual processing
 */
static GstFlowReturn
gst_templatematch_chain (GstPad * pad, GstBuffer * buf)
{
  StbtTemplateMatch *filter;
  GstMessage *m = NULL;

  filter = GST_TEMPLATEMATCH (GST_OBJECT_PARENT (pad));


  if ((!filter) || (!buf)) {
    return GST_FLOW_OK;
  }
  GST_DEBUG_OBJECT (filter, "Buffer size %u ", GST_BUFFER_SIZE (buf));

  GST_OBJECT_LOCK (filter);

  if (filter->singleFrameMode != GST_TM_SINGLE_FRAME_DISABLED) {
    while(!filter->singleFrameData) {
      g_cond_wait (&filter->singleFrameModeModified,
                   GST_OBJECT_GET_LOCK (filter));
    }
  }

  if (filter->capsInitialised && filter->templateImageAcquired) {
    CvPoint best_pos;
    gboolean matched = FALSE;
    double best_res;
    GstStructure *s;

    filter->cvImage->imageData = (char *) GST_BUFFER_DATA (buf);
    gst_templatematch_match (filter->cvImage, filter->cvTemplateImage,
        filter->cvDistImage, &best_res, &best_pos, filter->matchMethod);

    gst_templatematch_log_image (filter->cvImage,
        filter->debugDirectory, "source.png");
    gst_templatematch_log_image (filter->cvTemplateImage,
        filter->debugDirectory, "template.png");
    gst_templatematch_log_image (filter->cvDistImage, 
        filter->debugDirectory, "source_matchtemplate.png");
    
    if (best_res >= filter->matchThreshold) {
      matched = gst_templatematch_confirm (
          filter->cvImageROIGray, filter->cvImage, filter->cvTemplateImageGray,
          filter->confirmThreshold, &best_pos, filter->confirmMethod,
          filter->erodePasses, filter->debugDirectory);
    } else {
      matched = FALSE;
    }

    guint64 timestamp = GST_BUFFER_TIMESTAMP(buf);
    s = gst_structure_new ("template_match",
        "x", G_TYPE_UINT, best_pos.x,
        "y", G_TYPE_UINT, best_pos.y,
        "width", G_TYPE_UINT, filter->cvTemplateImage->width,
        "height", G_TYPE_UINT, filter->cvTemplateImage->height,
        "timestamp", G_TYPE_UINT64, timestamp,
        "first_pass_result", G_TYPE_DOUBLE, best_res,
        "template_path", G_TYPE_STRING, filter->template,
        "match", G_TYPE_BOOLEAN, matched, NULL);

    m = gst_message_new_element (GST_OBJECT (filter), s);

    if (filter->display) {
      CvPoint corner = best_pos;
      CvScalar color = CV_RGB(255, matched ? 0 : 255, 32);

      buf = gst_buffer_make_writable (buf);

      corner.x += filter->cvTemplateImage->width;
      corner.y += filter->cvTemplateImage->height;
      cvRectangle (filter->cvImage, best_pos, corner, color, 3, 8, 0);
    }

  }

  if (filter->singleFrameMode != GST_TM_SINGLE_FRAME_DISABLED) {
    filter->singleFrameMode = GST_TM_SINGLE_FRAME_WAIT;
    filter->singleFrameData = NULL;
  }

  GST_OBJECT_UNLOCK (filter);

  if (m) {
    gst_element_post_message (GST_ELEMENT (filter), m);
  }
  return gst_pad_push (filter->srcpad, buf);
}

static void
gst_templatematch_log_image (const IplImage * image,
    const char * debugDirectory, const char * filename)
{
  if (debugDirectory) {
    char *filepath;
    asprintf (&filepath, "%s/%s", debugDirectory, filename);

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

static void
gst_templatematch_match (IplImage * input, IplImage * template,
    IplImage * dist_image, double *best_res, CvPoint * best_pos, int method)
{
  double dist_min = 0, dist_max = 0;
  CvPoint min_pos, max_pos;
  cvMatchTemplate (input, template, dist_image, method);
  cvMinMaxLoc (dist_image, &dist_min, &dist_max, &min_pos, &max_pos, NULL);
  if ((CV_TM_SQDIFF_NORMED == method) || (CV_TM_SQDIFF == method)) {
    *best_res = dist_min;
    *best_pos = min_pos;
    if (CV_TM_SQDIFF_NORMED == method) {
      *best_res = 1 - *best_res;
    }
  } else {
    *best_res = dist_max;
    *best_pos = max_pos;
  }
}

/* Confirm the match returned by template match using specified method:
 * none : Do not confirm the match, assume correct
 * absdiff : Absolute difference between template and source
 * normed-absdiff : Absolute difference between normalised template and source
 * See specific confirm methods for more explanation
 */
static gboolean
gst_templatematch_confirm (IplImage * inputROIGray, IplImage * input,
    const IplImage * templateGray, float confirmThreshold,
    const CvPoint * bestPos, const int method,
    const int erodePasses, const char * debugDirectory)
{
  gboolean confirmed;
  switch (method) {
    case GST_TM_CONFIRM_METHOD_NONE:
      confirmed = TRUE;
      break;
    case GST_TM_CONFIRM_METHOD_ABSDIFF:
      confirmed = gst_templatematch_confirm_absdiff (
              inputROIGray, input, templateGray, confirmThreshold,
              bestPos, erodePasses, debugDirectory);
      break;
    case GST_TM_CONFIRM_METHOD_NORMED_ABSDIFF:
      confirmed = gst_templatematch_confirm_normed_absdiff (
              inputROIGray, input, templateGray, confirmThreshold,
              bestPos, erodePasses, debugDirectory);
      break;
    default:
      g_assert_not_reached ();
  }
  return confirmed;
}

/* The absolute difference between the template image and the source image
 * is computed. To account for the noise, the result is thresholded and
 * eroded. If the template is different enough, some white blobs with remain.
 */
static gboolean
gst_templatematch_confirm_absdiff (IplImage * inputROIGray, IplImage * input,
        const IplImage * templateGray, float confirmThreshold,
        const CvPoint * bestPos, const int erodePasses,
        const char * debugDirectory)
{
  IplImage *cvAbsDiffImage = inputROIGray;
  IplConvKernel *kernel = cvCreateStructuringElementEx (
      3, 3, 1, 1, CV_SHAPE_ELLIPSE, NULL );
  int threshold = (int)(confirmThreshold * 255);

  cvSetImageROI (input, cvRect (bestPos->x, bestPos->y, templateGray->width,
    templateGray->height));
  gst_templatematch_log_image (input, debugDirectory, "source_roi.png");

  cvCvtColor (input, inputROIGray, CV_BGR2GRAY);
  gst_templatematch_log_image (inputROIGray, debugDirectory, 
      "source_roi_gray.png");
  gst_templatematch_log_image (templateGray, debugDirectory, 
      "template_gray.png");

  cvAbsDiff (inputROIGray, templateGray, cvAbsDiffImage);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory, 
      "absdiff.png");
  
  cvThreshold (cvAbsDiffImage, cvAbsDiffImage, threshold, 255, 
      CV_THRESH_BINARY);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory, 
      "absdiff_threshold.png");
  
  cvErode (cvAbsDiffImage, cvAbsDiffImage, kernel, erodePasses);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory, 
      "absdiff_threshold_erode.png");

  cvResetImageROI (input);

  cvReleaseStructuringElement (&kernel);

  return cvCountNonZero (cvAbsDiffImage) == 0;
}

/* As with the regular absdiff confirm algorithm, except both template
 * and source images are normalised before the absolute difference/
 * threshold/erode is performed. This helps to accentuate differences
 * between images with low brightness variation, and requires a slightly
 * higher threshold value to eliminate the accentuated noise.
 */
static gboolean
gst_templatematch_confirm_normed_absdiff (IplImage * inputROIGray,
        IplImage * input, const IplImage * templateGray, float confirmThreshold,
        const CvPoint * bestPos, const int erodePasses,
        const char * debugDirectory)
{
  IplImage *templateGrayNormalized = cvCloneImage(templateGray);
  IplImage *inputROIGrayNormalized = inputROIGray;
  IplImage *cvAbsDiffImage = inputROIGray;
  IplConvKernel *kernel = cvCreateStructuringElementEx (
      3, 3, 1, 1, CV_SHAPE_ELLIPSE, NULL );
  int threshold = (int)(confirmThreshold * 255);

  cvSetImageROI (input, cvRect (bestPos->x, bestPos->y, templateGray->width,
    templateGray->height));
  gst_templatematch_log_image (input, debugDirectory, "source_roi.png");

  cvCvtColor (input, inputROIGray, CV_BGR2GRAY);
  gst_templatematch_log_image (inputROIGray, debugDirectory,
      "source_roi_gray.png");
  gst_templatematch_log_image (templateGray, debugDirectory,
      "template_gray.png");

  cvNormalize (inputROIGray, inputROIGrayNormalized,
      0, 255, CV_MINMAX, CV_8UC1);
  cvNormalize (templateGray, templateGrayNormalized,
      0, 255, CV_MINMAX, CV_8UC1);
  gst_templatematch_log_image(inputROIGrayNormalized,
      debugDirectory, "source_roi_gray_normalized.png");
  gst_templatematch_log_image(templateGrayNormalized,
      debugDirectory, "template_gray_normalized.png");

  cvAbsDiff (inputROIGrayNormalized, templateGrayNormalized,
      cvAbsDiffImage);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory,
      "absdiff.png");

  cvThreshold (cvAbsDiffImage, cvAbsDiffImage, threshold, 255,
      CV_THRESH_BINARY);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory,
      "absdiff_threshold.png");

  cvErode (cvAbsDiffImage, cvAbsDiffImage, kernel, erodePasses);
  gst_templatematch_log_image (cvAbsDiffImage, debugDirectory,
      "absdiff_threshold_erode.png");

  cvResetImageROI (input);

  cvReleaseStructuringElement (&kernel);

  return cvCountNonZero (cvAbsDiffImage) == 0;
}

/* We take ownership of debugDirectory here */
static void
gst_templatematch_set_debug_directory (
    StbtTemplateMatch * filter, char* debugDirectory)
{
  GST_OBJECT_LOCK (filter);
  if (filter->debugDirectory) {
    g_free (filter->debugDirectory);
  }
  filter->debugDirectory = debugDirectory;
  GST_OBJECT_UNLOCK (filter);
}

/* We take ownership of template here */
static void
gst_templatematch_load_template (StbtTemplateMatch * filter, char* template)
{
  IplImage *newTemplateImage = NULL;

  if (template) {
    newTemplateImage = cvLoadImage (template, CV_LOAD_IMAGE_COLOR);
    if (!newTemplateImage) {
      /* Unfortunately OpenCV doesn't seem to provide any way of finding out
         why the image load failed, so we can't be more specific than FAILED: */
      GST_ELEMENT_WARNING (filter, RESOURCE, FAILED,
          ("OpenCV failed to load template image"),
          ("While attempting to load template '%s'", template));
      GST_WARNING ("Couldn't load template image: %s. error: %s",
          template, g_strerror (errno));
      g_free (template);
      template = NULL;
    }
  }

  GST_OBJECT_LOCK(filter);
  if (filter->template) {
    g_free(filter->template);
    filter->template = NULL;
  }
  filter->template = template;
  if (filter->cvTemplateImage) {
    cvReleaseImage (&filter->cvTemplateImage);
    filter->cvTemplateImage = NULL;
  }
  filter->cvTemplateImage = newTemplateImage;
  gst_templatematch_rebuild_dist_image (filter);
  gst_templatematch_rebuild_template_images (filter);

  filter->templateImageAcquired = (filter->cvTemplateImage != NULL);

  GST_OBJECT_UNLOCK(filter);
}

/* Called when a new template image is provided
 * or when the capabilities are set.
 */
static void
gst_templatematch_rebuild_dist_image (StbtTemplateMatch * filter)
{
  if (filter->cvTemplateImage && filter->cvImage) {
    if (filter->cvTemplateImage->width > filter->cvImage->width) {
      GST_WARNING ("Template Image is wider than input image");
    } else if (filter->cvTemplateImage->height > filter->cvImage->height) {
      GST_WARNING ("Template Image is taller than input image");
    } else {
      if (filter->cvDistImage) {
        cvReleaseImage (&filter->cvDistImage);
  filter->cvDistImage = NULL;
      }
      GST_DEBUG_OBJECT (filter, "cvCreateImage (Size(%d-%d+1,%d) %d, %d)",
          filter->cvImage->width, filter->cvTemplateImage->width,
          filter->cvImage->height - filter->cvTemplateImage->height + 1,
          IPL_DEPTH_32F, 1);
      filter->cvDistImage =
          cvCreateImage (cvSize (filter->cvImage->width -
              filter->cvTemplateImage->width + 1,
              filter->cvImage->height - filter->cvTemplateImage->height + 1),
          IPL_DEPTH_32F, 1);
      if (!filter->cvDistImage) {
        GST_WARNING ("Couldn't create dist image.");
      }
    }
  }
}

static void
gst_templatematch_rebuild_template_images (StbtTemplateMatch * filter)
{
  if (filter->cvImageROIGray) {
    cvReleaseImage (&filter->cvImageROIGray);
    filter->cvImageROIGray = NULL;
  }
  if (filter->cvTemplateImageGray) {
    cvReleaseImage (&filter->cvTemplateImageGray);
    filter->cvTemplateImageGray = NULL;
  }
  if (filter->cvTemplateImage) {
    filter->cvImageROIGray = cvCreateImage (
      cvSize (filter->cvTemplateImage->width, filter->cvTemplateImage->height),
      IPL_DEPTH_8U, 1);
    filter->cvTemplateImageGray = cvCreateImage (
      cvSize (filter->cvTemplateImage->width, filter->cvTemplateImage->height),
      IPL_DEPTH_8U, 1);
    cvCvtColor (filter->cvTemplateImage,
        filter->cvTemplateImageGray, CV_BGR2GRAY);
  }
}


/* entry point to initialize the plug-in
 * initialize the plug-in itself
 * register the element factories and other features
 */
gboolean
gst_templatematch_plugin_init (GstPlugin * templatematch)
{
  /* debug category for fltering log messages */
  GST_DEBUG_CATEGORY_INIT (gst_templatematch_debug, "templatematch",
      0,
      "Performs template matching on videos and images, providing detected positions via bus messages");

  return gst_element_register (templatematch, "templatematch", GST_RANK_NONE,
      GST_TYPE_TEMPLATEMATCH);
}
