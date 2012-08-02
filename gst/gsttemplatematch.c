/*
 * GStreamer
 * Copyright (C) 2005 Thomas Vander Stichele <thomas@apestaart.org>
 * Copyright (C) 2005 Ronald S. Bultje <rbultje@ronald.bitfreak.net>
 * Copyright (C) 2008 Michael Sheldon <mike@mikeasoft.com>
 * Copyright (C) 2009 Noam Lewis <jones.noamle@gmail.com>
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
 * FIXME:Describe templatematch here.
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

#define DEFAULT_METHOD (3)

/* Filter signals and args */
enum
{
  /* FILL ME */
  LAST_SIGNAL
};

enum
{
  PROP_0,
  PROP_METHOD,
  PROP_TEMPLATE,
  PROP_DEBUG_DIRECTORY,
  PROP_DISPLAY,
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

GST_BOILERPLATE (GstTemplateMatch, gst_templatematch, GstElement,
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
static void gst_templatematch_set_debug_directory (GstTemplateMatch * filter, 
    const char* debugDirectory);

static void gst_templatematch_load_template (
    GstTemplateMatch * filter, const char * template);
static void gst_templatematch_match (IplImage * input, IplImage * template,
    IplImage * dist_image, double *best_res, CvPoint * best_pos, int method);
static double gst_templatematch_confirm(IplImage * input, 
    IplImage * template, CvPoint * best_pos, const char * debugDirectory);

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
gst_templatematch_class_init (GstTemplateMatchClass * klass)
{
  GObjectClass *gobject_class;

  gobject_class = (GObjectClass *) klass;

  gobject_class->finalize = gst_templatematch_finalize;
  gobject_class->set_property = gst_templatematch_set_property;
  gobject_class->get_property = gst_templatematch_get_property;

  g_object_class_install_property (gobject_class, PROP_METHOD,
      g_param_spec_int ("method", "Method",
          "Specifies the way the template must be compared with image regions. 0=SQDIFF, 1=SQDIFF_NORMED, 2=CCOR, 3=CCOR_NORMED, 4=CCOEFF, 5=CCOEFF_NORMED.",
          0, 5, DEFAULT_METHOD, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
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
          "Sets whether the detected template should be highlighted in the output",
          TRUE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
}

/* initialize the new element
 * instantiate pads and add them to element
 * set pad callback functions
 * initialize instance structure
 */
static void
gst_templatematch_init (GstTemplateMatch * filter,
    GstTemplateMatchClass * gclass)
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
  filter->method = DEFAULT_METHOD;
  filter->debugDirectory = NULL;
}

static void
gst_templatematch_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  GstTemplateMatch *filter = GST_TEMPLATEMATCH (object);

  switch (prop_id) {
    case PROP_METHOD:
      GST_OBJECT_LOCK(filter);
      switch (g_value_get_int (value)) {
        case 0:
          filter->method = CV_TM_SQDIFF;
          break;
        case 1:
          filter->method = CV_TM_SQDIFF_NORMED;
          break;
        case 2:
          filter->method = CV_TM_CCORR;
          break;
        case 3:
          filter->method = CV_TM_CCORR_NORMED;
          break;
        case 4:
          filter->method = CV_TM_CCOEFF;
          break;
        case 5:
          filter->method = CV_TM_CCOEFF_NORMED;
          break;
      }
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
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_templatematch_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
  GstTemplateMatch *filter = GST_TEMPLATEMATCH (object);

  switch (prop_id) {
    case PROP_METHOD:
      g_value_set_int (value, filter->method);
      break;
    case PROP_TEMPLATE:
      g_value_set_string (value, filter->template);
      break;
    case PROP_DISPLAY:
      g_value_set_boolean (value, filter->display);
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
  GstTemplateMatch *filter;
  GstPad *otherpad;
  gint width, height;
  GstStructure *structure;

  filter = GST_TEMPLATEMATCH (gst_pad_get_parent (pad));
  structure = gst_caps_get_structure (caps, 0);
  gst_structure_get_int (structure, "width", &width);
  gst_structure_get_int (structure, "height", &height);

  filter->cvImage =
      cvCreateImageHeader (cvSize (width, height), IPL_DEPTH_8U, 3);

  otherpad = (pad == filter->srcpad) ? filter->sinkpad : filter->srcpad;
  gst_object_unref (filter);

  return gst_pad_set_caps (otherpad, caps);
}

static void
gst_templatematch_finalize (GObject * object)
{
  GstTemplateMatch *filter;
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
}

/* chain function
 * this function does the actual processing
 */
static GstFlowReturn
gst_templatematch_chain (GstPad * pad, GstBuffer * buf)
{
  GstTemplateMatch *filter;
  CvPoint best_pos;
  double best_res;
  GstMessage *m = NULL;

  filter = GST_TEMPLATEMATCH (GST_OBJECT_PARENT (pad));

  if ((!filter) || (!buf)) {
    return GST_FLOW_OK;
  }
  GST_DEBUG_OBJECT (filter, "Buffer size %u ", GST_BUFFER_SIZE (buf));

  filter->cvImage->imageData = (char *) GST_BUFFER_DATA (buf);

  GST_OBJECT_LOCK(filter);
  if (filter->cvTemplateImage && !filter->cvDistImage) {
    if (filter->cvTemplateImage->width > filter->cvImage->width) {
      GST_WARNING ("Template Image is wider than input image");
    } else if (filter->cvTemplateImage->height > filter->cvImage->height) {
      GST_WARNING ("Template Image is taller than input image");
    } else {

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
  if (filter->cvTemplateImage && filter->cvImage && filter->cvDistImage) {
    GstStructure *s;

    gst_templatematch_match (filter->cvImage, filter->cvTemplateImage,
        filter->cvDistImage, &best_res, &best_pos, filter->method);

    gst_templatematch_log_image (filter->cvImage,
        filter->debugDirectory, "source.png");
    gst_templatematch_log_image (filter->cvTemplateImage,
        filter->debugDirectory, "template.png");
    gst_templatematch_log_image( filter->cvDistImage, 
        filter->debugDirectory, "source_matchtemplate.png");
    
    if (best_res >= 0.80 && best_res <= 0.99) {
      double resultPass2 = gst_templatematch_confirm(filter->cvImage, 
          filter->cvTemplateImage, &best_pos, filter->debugDirectory);
      if (resultPass2 >= 0.80) {
        best_res = 1.0;
      } else {
        best_res = resultPass2;
      }
    }

    s = gst_structure_new ("template_match",
        "x", G_TYPE_UINT, best_pos.x,
        "y", G_TYPE_UINT, best_pos.y,
        "width", G_TYPE_UINT, filter->cvTemplateImage->width,
        "height", G_TYPE_UINT, filter->cvTemplateImage->height,
        "result", G_TYPE_DOUBLE, best_res, NULL);

    m = gst_message_new_element (GST_OBJECT (filter), s);

    if (filter->display) {
      CvPoint corner = best_pos;
      CvScalar color = CV_RGB(255, 255-pow(255,best_res), 32);

      buf = gst_buffer_make_writable (buf);

      corner.x += filter->cvTemplateImage->width;
      corner.y += filter->cvTemplateImage->height;
      cvRectangle (filter->cvImage, best_pos, corner, color, 3, 8, 0);
    }

  }
  GST_OBJECT_UNLOCK(filter);

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

    IplImage *imageToLog = image;
    if (image->depth == IPL_DEPTH_32F) {
      imageToLog = cvCreateImage (
          cvSize (image->width, image->height), IPL_DEPTH_8U, 1);
      cvConvertScale (image, imageToLog, 255.0, 0);
    }
    cvSaveImage (filepath, imageToLog, NULL);
    if (imageToLog != image) {
      cvReleaseImage (&imageToLog);
    }
    free (filepath);
  }
}

static IplImage  *
gst_templatematch_copy_image_roi (
    IplImage * input, int x, int y, int width, int height)
{
  IplImage *inputROI = cvCreateImage (
      cvSize (width, height), input->depth, input->nChannels);
  cvSetImageROI (input, cvRect(x, y, width, height));
  cvCopy (input, inputROI, NULL);
  cvResetImageROI (input);
  return inputROI;
}

static IplImage  *
gst_templatematch_extract_edges (IplImage * input)
{
  IplImage      *resultCanny;
  IplImage      *inputGray;
  IplConvKernel *crossElement;

  // Apply canny on the image
  inputGray = cvCreateImage (
      cvSize (input->width, input->height), IPL_DEPTH_8U, 1);
  cvCvtColor (input, inputGray, CV_BGR2GRAY);
  resultCanny = cvCreateImage (
      cvSize (input->width, input->height), IPL_DEPTH_8U, 1);
  cvCanny (inputGray, resultCanny, 150, 200, 3);
  cvReleaseImage (&inputGray);

  // Dilate the image
  crossElement = cvCreateStructuringElementEx (
      3, 3, 1, 1, CV_SHAPE_CROSS, NULL);
  cvDilate (resultCanny, resultCanny, crossElement, 1);
  cvReleaseStructuringElement (&crossElement);

  return resultCanny;
}

/**
 * @brief Compute the number of times to split an image
 *        to get maximum subimages of size split_limit.
 * @note  With a size of 350, and a split limit of 100,
 *        the split number will be 3.
 *        With a size of 100, and a split limit of 100,
 *        the split number will be 0.
 */
static int
gst_templatematch_compute_image_split_number (
    int size, int splitLimit)
{
  return (int)( ceil((float)size / splitLimit ) - 1 );
}

static void
gst_templatematch_compute_split_size_and_position (
    int splitNo, int splitNumber, int imageSize,
    int *splitSize, int *splitPosition)
{
  *splitSize = floor (imageSize / (splitNumber + 1));
  *splitPosition = *splitSize * splitNo;
  if (splitNo == splitNumber) {
    *splitSize = imageSize - splitNumber * *splitSize;
  }
}

static double
gst_templatematch_compute_lowest_match_of_all_subimages (
    IplImage * inputEdges, IplImage * templateEdges, IplImage  * distImage,
    const char * debugDirectory)
{
  // inputEdges should have the same size as templateEdges
  double minBestRes = 1.0;
  int xsplitNumber =
      gst_templatematch_compute_image_split_number (templateEdges->width, 100);
  int ysplitNumber =
      gst_templatematch_compute_image_split_number (templateEdges->height, 100);
  int xsplitNo, ysplitNo;

  // Apply the template match on every subimage
  for (xsplitNo = 0; xsplitNo < xsplitNumber + 1; ++xsplitNo) {
    for (ysplitNo = 0; ysplitNo < ysplitNumber + 1; ++ysplitNo) {
      int currentSplitX = -1;
      int currentSplitY = -1;
      int currentSplitWidth = -1;
      int currentSplitHeight = -1;
      CvPoint bestPos;
      double currentRes = -1.0;
      char imageName[256];

      gst_templatematch_compute_split_size_and_position (
          xsplitNo, xsplitNumber, templateEdges->width,
          &currentSplitWidth, &currentSplitX);
      gst_templatematch_compute_split_size_and_position (
          ysplitNo, ysplitNumber, templateEdges->height,
          &currentSplitHeight, &currentSplitY);

      cvSetImageROI (inputEdges, cvRect (
          currentSplitX, currentSplitY, currentSplitWidth, currentSplitHeight));
      cvSetImageROI (templateEdges, cvRect (
          currentSplitX, currentSplitY, currentSplitWidth, currentSplitHeight));

      snprintf (imageName, 256, "source_roi_canny_dilate_roi_%d_%d.png",
          currentSplitX, currentSplitY);
      gst_templatematch_log_image (inputEdges, debugDirectory, imageName);

      snprintf (imageName, 256, "template_canny_dilate_roi_%d_%d.png",
          currentSplitX, currentSplitY);
      gst_templatematch_log_image (templateEdges, debugDirectory, imageName);

      gst_templatematch_match (
          inputEdges, templateEdges, distImage, &currentRes, &bestPos, 1);
      if (currentRes < minBestRes) {
        minBestRes = currentRes;
      }

      snprintf (imageName, 256,
          "source_roi_canny_dilate_roi_%d_%d_matchtemplate.png",
          currentSplitX, currentSplitY);
      gst_templatematch_log_image (distImage, debugDirectory, imageName);

      cvResetImageROI (templateEdges);
      cvResetImageROI (inputEdges);
    }
  }
  return minBestRes;
}

static double
gst_templatematch_confirm(IplImage * input, IplImage * template,
    CvPoint * bestPos, const char * debugDirectory)
{
  double minBestRes     = 1.0;
  IplImage  * inputROI  = gst_templatematch_copy_image_roi(
      input, bestPos->x, bestPos->y, template->width, template->height);
  IplImage  * inputEdges    = gst_templatematch_extract_edges(inputROI);
  IplImage  * templateEdges = gst_templatematch_extract_edges(template);
  IplImage  * distImage     = cvCreateImage( cvSize (1, 1), IPL_DEPTH_32F, 1);

  gst_templatematch_log_image( inputROI, debugDirectory, "source_roi.png");
  gst_templatematch_log_image( inputEdges, debugDirectory, "source_roi_canny_dilate.png");
  gst_templatematch_log_image( templateEdges, debugDirectory, "template_canny_dilate.png");

  minBestRes = gst_templatematch_compute_lowest_match_of_all_subimages(
    inputEdges, templateEdges, distImage, debugDirectory);
  
  cvReleaseImage(&distImage);
  cvReleaseImage(&templateEdges);
  cvReleaseImage(&inputEdges);
  cvReleaseImage(&inputROI);

  return minBestRes;
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

/* We take ownership of debugDirectory here */
static void
gst_templatematch_set_debug_directory (
    GstTemplateMatch * filter, const char* debugDirectory)
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
gst_templatematch_load_template (GstTemplateMatch * filter, const char* template)
{
  const char *oldTemplateFilename = NULL;
  IplImage *oldTemplateImage = NULL, *newTemplateImage = NULL, *oldDistImage = NULL;

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
  oldTemplateFilename = filter->template;
  filter->template = template;
  oldTemplateImage = filter->cvTemplateImage;
  filter->cvTemplateImage = newTemplateImage;
  oldDistImage = filter->cvDistImage;
  /* This will be recreated in the chain function as required: */
  filter->cvDistImage = NULL;
  GST_OBJECT_UNLOCK(filter);

  cvReleaseImage (&oldDistImage);
  cvReleaseImage (&oldTemplateImage);
  g_free(oldTemplateFilename);
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
