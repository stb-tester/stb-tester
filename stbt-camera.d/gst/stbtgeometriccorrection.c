/* stb-tester
 * Copyright (C) 2014 stb-tester.com Ltd. <will@williammanley.net>
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
 * Free Software Foundation, Inc., 51 Franklin Street, Suite 500,
 * Boston, MA 02110-1335, USA.
 */
/**
 * SECTION:element-stbtgeometriccorrection
 *
 * The geometriccorrection element supports videoing TVs with webcams.  Based on data
 * about the camera and the location of the TV in the image it will output what
 * is being shown on the TV.
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch -v v4l2src ! video/x-raw,width=1080,height=720 ! videoconvert \
 *     ! geometriccorrection camera-matrix="1650.9498393436943 0.0 929.0144682177463 0.0 1650.0877603121983 558.55148343511712 0.0 0.0 1.0" \
 *                  distortion-coefficients="0.10190074279957002 -0.18199960394082984 0.00054709946447197304 0.00039158751563262209 -0.0479346424607551" \
 *                  inv-homography-matrix="1363.1288390747131 7.438063312178901 643.25417659039442 38.730496461642169 1354.6127277059686 388.87669488396085 0.040142377232467538 0.043862451595691403 1.0" \
 *     ! videoconvert ! autoimagesink
 * ]|
 * Captures a video of a TV from your webcam and shows you a video of what's
 * on TV.
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/video/gstvideofilter.h>

#include <opencv2/imgproc/imgproc_c.h>
#include <opencv2/calib3d/calib3d.hpp>
#include <stdio.h>

#include "stbtgeometriccorrection.h"

GST_DEBUG_CATEGORY_STATIC (stbt_geometric_correction_debug_category);
#define GST_CAT_DEFAULT stbt_geometric_correction_debug_category

#define STBT_GEOMETRIC_CORRECTION_LATENCY (40*GST_MSECOND)

/* prototypes */
static void stbt_geometric_correction_finalize (GObject * gobject);

static void stbt_geometric_correction_set_property (GObject * object,
    guint property_id, const GValue * value, GParamSpec * pspec);
static void stbt_geometric_correction_get_property (GObject * object,
    guint property_id, GValue * value, GParamSpec * pspec);
static gboolean stbt_geometric_correction_query (GstBaseTransform * trans,
    GstPadDirection direction, GstQuery * query);

static gboolean stbt_geometric_correction_start (GstBaseTransform * trans);
static gboolean stbt_geometric_correction_stop (GstBaseTransform * trans);
static GstCaps *stbt_watch_transform_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * filter);

static GstFlowReturn stbt_geometric_correction_transform_frame (GstVideoFilter * filter,
    GstVideoFrame * inframe, GstVideoFrame * outframe);

enum
{
  PROP_0,
  PROP_CAMERA_MATRIX,
  PROP_DISTORTION_COEFFICIENTS,
  PROP_INV_HOMOGRAPHY_MATRIX
};

/* pad templates */

#define VIDEO_SRC_CAPS \
    "video/x-raw, format=(string)BGR, width=(int)1280, height=(int)720"

#define VIDEO_SINK_CAPS \
    "video/x-raw, format=(string)BGR, width=(int)1920, height=(int)1080"

/* Property defaults - Scales 1920x1080 to 1280x720, the equivalent of a noop
   for this element */

#define DEFAULT_CAMERA_MATRIX \
    "1.0   0.0   0.0 " \
    "0.0   1.0   0.0 " \
    "0.0   0.0   1.0 "

#define DEFAULT_DISTORTION_COEFFICIENTS \
    "0.0   0.0   0.0   0.0   0.0"

#define DEFAULT_INV_HOMOGRAPHY_MATRIX \
    "1.5  0.0  0.25 " \
    "0.0  1.5  0.25 " \
    "0.0  0.0  1.0  "

/* class initialization */

G_DEFINE_TYPE_WITH_CODE (StbtGeometricCorrection, stbt_geometric_correction,
    GST_TYPE_VIDEO_FILTER,
    GST_DEBUG_CATEGORY_INIT (stbt_geometric_correction_debug_category, "stbtgeometriccorrection",
        0, "debug category for geometriccorrection element"));

static void
stbt_geometric_correction_class_init (StbtGeometricCorrectionClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstBaseTransformClass *base_transform_class =
      GST_BASE_TRANSFORM_CLASS (klass);
  GstVideoFilterClass *video_filter_class = GST_VIDEO_FILTER_CLASS (klass);

  /* Setting up pads and setting metadata should be moved to
     base_class_init if you intend to subclass this class. */
  gst_element_class_add_pad_template (GST_ELEMENT_CLASS (klass),
      gst_pad_template_new ("src", GST_PAD_SRC, GST_PAD_ALWAYS,
          gst_caps_from_string (VIDEO_SRC_CAPS)));
  gst_element_class_add_pad_template (GST_ELEMENT_CLASS (klass),
      gst_pad_template_new ("sink", GST_PAD_SINK, GST_PAD_ALWAYS,
          gst_caps_from_string (VIDEO_SINK_CAPS)));

  gst_element_class_set_static_metadata (GST_ELEMENT_CLASS (klass),
      "Geometric Correction", "Generic",
      "Input: pictures of a TV output: what is playing on that TV",
      "William Manley <will@williammanley.net>");

  gobject_class->set_property = GST_DEBUG_FUNCPTR (stbt_geometric_correction_set_property);
  gobject_class->get_property = GST_DEBUG_FUNCPTR (stbt_geometric_correction_get_property);
  gobject_class->finalize = GST_DEBUG_FUNCPTR (stbt_geometric_correction_finalize);

  base_transform_class->start = GST_DEBUG_FUNCPTR (stbt_geometric_correction_start);
  base_transform_class->stop = GST_DEBUG_FUNCPTR (stbt_geometric_correction_stop);
  base_transform_class->query = GST_DEBUG_FUNCPTR (stbt_geometric_correction_query);
  base_transform_class->transform_caps =
      GST_DEBUG_FUNCPTR (stbt_watch_transform_caps);
  video_filter_class->transform_frame =
      GST_DEBUG_FUNCPTR (stbt_geometric_correction_transform_frame);

  g_object_class_install_property (gobject_class, PROP_CAMERA_MATRIX,
      g_param_spec_string ("camera-matrix", "Camera Matrix",
          "The camera matrix of the camera used to capture the input",
          DEFAULT_CAMERA_MATRIX, G_PARAM_READWRITE | G_PARAM_CONSTRUCT));
  g_object_class_install_property (gobject_class, PROP_DISTORTION_COEFFICIENTS,
      g_param_spec_string ("distortion-coefficients", "Distortion Coefficients",
          "The distortion coefficients of the camera used to capture the input",
          DEFAULT_DISTORTION_COEFFICIENTS,
          G_PARAM_READWRITE | G_PARAM_CONSTRUCT));
  g_object_class_install_property (gobject_class, PROP_INV_HOMOGRAPHY_MATRIX,
      g_param_spec_string ("inv-homography-matrix", "Homography Matrix",
          "The inverse homography matrix describing the region of interest",
          DEFAULT_INV_HOMOGRAPHY_MATRIX, G_PARAM_READWRITE | G_PARAM_CONSTRUCT));
}

static void
stbt_geometric_correction_init (StbtGeometricCorrection * geometriccorrection)
{
  g_mutex_init(&geometriccorrection->props_mutex);
}

static void
stbt_geometric_correction_finalize (GObject * object)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (object);
  g_mutex_clear(&geometriccorrection->props_mutex);
  G_OBJECT_CLASS (stbt_geometric_correction_parent_class)->finalize (object);
}

static void
stbt_geometric_correction_set_property (GObject * object, guint property_id,
    const GValue * value, GParamSpec * pspec)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (object);
  int values_read;
  float (*m)[3] = NULL;
  float *d;

  GST_DEBUG_OBJECT (geometriccorrection, "set_property");

  g_mutex_lock(&geometriccorrection->props_mutex);
  geometriccorrection->needs_regen = TRUE;
  switch (property_id) {
    case PROP_CAMERA_MATRIX:
      m = geometriccorrection->camera_matrix;
    case PROP_INV_HOMOGRAPHY_MATRIX:
      m = m ? m : geometriccorrection->inv_homography_matrix;

      values_read = sscanf (g_value_get_string (value),
          "%f %f %f %f %f %f %f %f %f",
          &m[0][0], &m[0][1], &m[0][2],
          &m[1][0], &m[1][1], &m[1][2], &m[2][0], &m[2][1], &m[2][2]);
      g_warn_if_fail (values_read == 9);
      break;
    case PROP_DISTORTION_COEFFICIENTS:
      d = geometriccorrection->distortion_coefficients;
      values_read = sscanf (g_value_get_string (value),
          "%f %f %f %f %f", &d[0], &d[1], &d[2], &d[3], &d[4]);
      g_warn_if_fail (values_read == 5);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      return;
  }
  geometriccorrection->needs_regen = TRUE;
  g_mutex_unlock(&geometriccorrection->props_mutex);
}

static void
stbt_geometric_correction_get_property (GObject * object, guint property_id,
    GValue * value, GParamSpec * pspec)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (object);
  float (*m)[3] = NULL;
  float *d;
  gchar *str = NULL;

  GST_DEBUG_OBJECT (geometriccorrection, "get_property");

  g_mutex_lock(&geometriccorrection->props_mutex);
  switch (property_id) {
    case PROP_CAMERA_MATRIX:
      m = geometriccorrection->camera_matrix;
    case PROP_INV_HOMOGRAPHY_MATRIX:
      m = m ? m : geometriccorrection->inv_homography_matrix;

      str = g_strdup_printf ("%f %f %f %f %f %f %f %f %f",
          m[0][0], m[0][1], m[0][2],
          m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2]);
      g_value_take_string (value, str);
      break;
    case PROP_DISTORTION_COEFFICIENTS:
      d = geometriccorrection->distortion_coefficients;
      str = g_strdup_printf ("%f %f %f %f %f", d[0], d[1], d[2], d[3], d[4]);
      g_value_take_string (value, str);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      return;
  }
  g_mutex_unlock(&geometriccorrection->props_mutex);
}

static gboolean
stbt_geometric_correction_query (GstBaseTransform * trans, GstPadDirection direction,
    GstQuery * query)
{
  gboolean result = GST_BASE_TRANSFORM_CLASS (stbt_geometric_correction_parent_class)
      ->query (trans, direction, query);

  if (result && GST_QUERY_TYPE (query) == GST_QUERY_LATENCY) {
    GstClockTime min, max;
    gboolean live;

    gst_query_parse_latency (query, &live, &min, &max);

    min += STBT_GEOMETRIC_CORRECTION_LATENCY;
    max += STBT_GEOMETRIC_CORRECTION_LATENCY;

    gst_query_set_latency (query, live, min, max);
  }

  return result;
}

typedef struct Coord_
{
  float x;
  float y;
} Coord;

typedef struct Coord3_
{
  float x;
  float y;
  float z;
} Coord3;

static void
regenerate_remapping_matrix (StbtGeometricCorrection * geometriccorrection)
{
  int x, y;
  CvMat *remapping = cvCreateMat (720, 1280, CV_32FC2);
  CvMat *remapping_int = cvCreateMat (720, 1280, CV_16SC2);
  CvMat *remapping_interpolation = cvCreateMat (720, 1280, CV_16UC1);
  CvMat remapping_flat = cvMat (1, 1280 * 720, CV_32FC2, remapping->data.fl);
  CvMat *temp;
  CvMat camera_matrix = cvMat (3, 3, CV_32F, geometriccorrection->camera_matrix);
  CvMat distortion_coefficients =
      cvMat (5, 1, CV_32F, geometriccorrection->distortion_coefficients);
  CvMat inv_homography_matrix = cvMat (3, 3, CV_32F, geometriccorrection->inv_homography_matrix);
  float no_transform_data[3] = { 0.0, 0.0, 0.0 };
  CvMat no_transform = cvMat (3, 1, CV_32F, no_transform_data);

  for (x = 0; x < 1280; x++) {
    for (y = 0; y < 720; y++) {
      CV_MAT_ELEM (*remapping, Coord, y, x).x = x;
      CV_MAT_ELEM (*remapping, Coord, y, x).y = y;
    }
  }

  /* remap takes a matrix of (x, y) coordinates.  The value of any pixel in the
     output will be taken from the input image at the coordinates in the
     remapping matrix.  Therefore we need to modify the coordinates in the
     "identity" mapping created above until they point at the locations in the
     source image that we want to get the values from.

     By transforming coordinates from dest to src remap will transform values
     from src to dest. */
  cvPerspectiveTransform ((const CvArr *) remapping, (CvArr *) remapping,
      &inv_homography_matrix);

  temp = cvCreateMat (1, 1280 * 720, CV_32FC3);
  for (x = 0; x < 1280; x++) {
    for (y = 0; y < 720; y++) {
      CV_MAT_ELEM (*temp, Coord3, 0, x + 1280 * y).x =
          CV_MAT_ELEM (*remapping, Coord, y, x).x;
      CV_MAT_ELEM (*temp, Coord3, 0, x + 1280 * y).y =
          CV_MAT_ELEM (*remapping, Coord, y, x).y;
      CV_MAT_ELEM (*temp, Coord3, 0, x + 1280 * y).z = 0.0;
    }
  }

  cvProjectPoints2 ((const CvArr *) temp, &no_transform, &no_transform,
      &camera_matrix, &distortion_coefficients, (CvArr *) & remapping_flat,
      NULL, NULL, NULL, NULL, NULL, 0);
  cvReleaseMat (&temp);

  cvConvertMaps (remapping, NULL, remapping_int, remapping_interpolation);
  cvReleaseMat (&remapping);

  cvReleaseMat (&geometriccorrection->remapping_int);
  cvReleaseMat (&geometriccorrection->remapping_interpolation);
  geometriccorrection->remapping_int = remapping_int;
  geometriccorrection->remapping_interpolation = remapping_interpolation;
}

static gboolean
stbt_geometric_correction_start (GstBaseTransform * trans)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (trans);

  GST_DEBUG_OBJECT (geometriccorrection, "start");

  g_return_val_if_fail (geometriccorrection->remapping_int == NULL, FALSE);
  g_return_val_if_fail (geometriccorrection->remapping_interpolation == NULL, FALSE);
  regenerate_remapping_matrix (geometriccorrection);

  return TRUE;
}

static gboolean
stbt_geometric_correction_stop (GstBaseTransform * trans)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (trans);

  GST_DEBUG_OBJECT (geometriccorrection, "stop");

  cvReleaseMat (&geometriccorrection->remapping_int);
  cvReleaseMat (&geometriccorrection->remapping_interpolation);

  return TRUE;
}

static GstCaps *
stbt_watch_transform_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * filter)
{
  GstCaps *ret = gst_caps_copy (caps);
  GValue res = G_VALUE_INIT;

  g_value_init (&res, G_TYPE_INT);

  if (direction == GST_PAD_SRC) {
    g_value_set_int (&res, 1920);
    gst_caps_set_value (ret, "width", &res);
    g_value_set_int (&res, 1080);
    gst_caps_set_value (ret, "height", &res);
  } else {
    g_value_set_int (&res, 1280);
    gst_caps_set_value (ret, "width", &res);
    g_value_set_int (&res, 720);
    gst_caps_set_value (ret, "height", &res);
  }

  if (filter) {
    GstCaps *intersection;

    intersection =
        gst_caps_intersect_full (filter, ret, GST_CAPS_INTERSECT_FIRST);
    gst_caps_unref (ret);
    ret = intersection;
  }

  return ret;
}

/* transform */
static GstFlowReturn
stbt_geometric_correction_transform_frame (GstVideoFilter * filter,
    GstVideoFrame * inframe, GstVideoFrame * outframe)
{
  StbtGeometricCorrection *geometriccorrection = STBT_GEOMETRIC_CORRECTION (filter);
  CvMat inmat = cvMat (1080, 1920, CV_8UC3, inframe->data[0]);
  CvMat outmat = cvMat (720, 1280, CV_8UC3, outframe->data[0]);

  GST_DEBUG_OBJECT (geometriccorrection, "transform_frame");

  g_mutex_lock(&geometriccorrection->props_mutex);
  if (geometriccorrection->needs_regen) {
    regenerate_remapping_matrix(geometriccorrection);
    geometriccorrection->needs_regen = FALSE;
  }
  g_mutex_unlock(&geometriccorrection->props_mutex);

  g_return_val_if_fail (geometriccorrection->remapping_int, GST_FLOW_ERROR);
  g_return_val_if_fail (geometriccorrection->remapping_interpolation, GST_FLOW_ERROR);
  g_return_val_if_fail (inframe->info.width == 1920 &&
      inframe->info.height == 1080, GST_FLOW_ERROR);
  g_return_val_if_fail (outframe->info.width == 1280 &&
      outframe->info.height == 720, GST_FLOW_ERROR);

  cvRemap (&inmat, &outmat, geometriccorrection->remapping_int,
      geometriccorrection->remapping_interpolation,
      CV_INTER_LINEAR + CV_WARP_FILL_OUTLIERS, cvScalarAll (0));

  return GST_FLOW_OK;
}
