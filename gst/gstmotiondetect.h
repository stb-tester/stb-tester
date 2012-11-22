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

#ifndef __GST_MOTIONDETECT_H__
#define __GST_MOTIONDETECT_H__

#include <gst/gst.h>
#include <gst/base/gstbasetransform.h>
#include <cv.h>
#include <highgui.h>

G_BEGIN_DECLS

#define GST_TYPE_MOTIONDETECT \
  (gst_motiondetect_get_type())
#define GST_MOTIONDETECT(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_MOTIONDETECT,StbtMotionDetect))
#define GST_MOTIONDETECT_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_MOTIONDETECT,StbtMotionDetectClass))
#define GST_IS_MOTIONDETECT(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_MOTIONDETECT))
#define GST_IS_MOTIONDETECT_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_MOTIONDETECT))

typedef struct _StbtMotionDetect StbtMotionDetect;
typedef struct _StbtMotionDetectClass StbtMotionDetectClass;

enum
{
    MOTION_DETECT_STATE_INITIALISING,
    MOTION_DETECT_STATE_ACQUIRING_REFERENCE_IMAGE,
    MOTION_DETECT_STATE_REFERENCE_IMAGE_ACQUIRED,
};

/**
 * StbtMotionDetect:
 *
 * Opaque data structure
 */
struct _StbtMotionDetect {
  GstBaseTransform element;
  
  gfloat noiseThreshold;

  gboolean enabled;
  int state;
  IplImage *cvCurrentImage;
  IplImage *cvReferenceImageGray, *cvCurrentImageGray, *cvMaskImage;
  IplImage *cvInvertedMaskImage;
  char *mask;
  char *debugDirectory;
  gboolean display;
};

struct _StbtMotionDetectClass {
  GstBaseTransformClass parent_class;
};

GType gst_motiondetect_get_type(void);

G_END_DECLS

#endif /* __GST_MOTIONDETECT_H__ */
