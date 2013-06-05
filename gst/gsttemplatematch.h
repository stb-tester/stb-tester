/*
 * GStreamer
 * Copyright (C) 2005 Thomas Vander Stichele <thomas@apestaart.org>
 * Copyright (C) 2005 Ronald S. Bultje <rbultje@ronald.bitfreak.net>
 * Copyright (C) 2008 Michael Sheldon <mike@mikeasoft.com>
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

#ifndef __GST_TEMPLATEMATCH_H__
#define __GST_TEMPLATEMATCH_H__

#include <gst/gst.h>
#include <cv.h>
#include <highgui.h>

G_BEGIN_DECLS
/* #defines don't like whitespacey bits */
#define GST_TYPE_TEMPLATEMATCH \
  (gst_templatematch_get_type())
#define GST_TEMPLATEMATCH(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_TEMPLATEMATCH,StbtTemplateMatch))
#define GST_TEMPLATEMATCH_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_TEMPLATEMATCH,StbtTemplateMatchClass))
#define GST_IS_TEMPLATEMATCH(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_TEMPLATEMATCH))
#define GST_IS_TEMPLATEMATCH_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_TEMPLATEMATCH))

/* stbt's wrappers for OpenCV's cvMatchTemplate method enums,
 * which wrap the enums as G_TYPE_ENUMs,
 * associated with `filter->matchMethod`
 */
typedef enum {
  GST_TM_MATCH_METHOD_CV_TM_SQDIFF_NORMED = CV_TM_SQDIFF_NORMED,
  GST_TM_MATCH_METHOD_CV_TM_CCORR_NORMED = CV_TM_CCORR_NORMED,
  GST_TM_MATCH_METHOD_CV_TM_CCOEFF_NORMED = CV_TM_CCOEFF_NORMED,
} GstTMMatchMethod;

/* stbt's enums for confirming a template match result
 * associated with `filter->confirmMethod`
 */
typedef enum {
  GST_TM_CONFIRM_METHOD_NONE,
  GST_TM_CONFIRM_METHOD_ABSDIFF,
  GST_TM_CONFIRM_METHOD_NORMED_ABSDIFF
} GstTMConfirmMethod;


/*
 * stbt's enums for specifying the "single frame" operating mode
 */
typedef enum {
  GST_TM_SINGLE_FRAME_DISABLED,
  GST_TM_SINGLE_FRAME_NEXT,
  GST_TM_SINGLE_FRAME_WAIT
} GstTMSingleFrameMode;

typedef struct _StbtTemplateMatch StbtTemplateMatch;
typedef struct _StbtTemplateMatchClass StbtTemplateMatchClass;

struct _StbtTemplateMatch
{
  GstElement element;

  GstPad *sinkpad, *srcpad;

  GstTMMatchMethod matchMethod;
  gfloat matchThreshold;
  GstTMConfirmMethod confirmMethod;
  gint erodePasses;
  gfloat confirmThreshold;
  gboolean display;
  GstTMSingleFrameMode singleFrameMode;
  GCond singleFrameModeModified;
  gpointer singleFrameData;

  gchar *template;
  gchar *debugDirectory;

  IplImage *cvImage, *cvTemplateImage, *cvDistImage;
  IplImage *cvImageROIGray, *cvTemplateImageGray;
  gboolean capsInitialised, templateImageAcquired;
};

struct _StbtTemplateMatchClass
{
  GstElementClass parent_class;
};

GType gst_templatematch_get_type (void);

gboolean gst_templatematch_plugin_init (GstPlugin * templatematch);

G_END_DECLS
#endif /* __GST_TEMPLATEMATCH_H__ */
