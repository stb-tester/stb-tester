#!/usr/bin/python
##
##  Copyright (c) 2010 The WebM project authors. All Rights Reserved.
##
##  Use of this source code is governed by a BSD-style license
##  that can be found in the LICENSE file in the root of the source
##  tree. An additional intellectual property rights grant can be found
##  in the file PATENTS.  All contributing project authors may
##  be found in the AUTHORS file in the root of the source tree.
##

"""One-line documentation for webmtool module.

A detailed description of webmtool.
"""

__author__ = 'hwasoolee@google.com (Hwasoo Lee)'

from webm import *

def main():
  import sys
  menu = 'none'
  num_argument = len(sys.argv)
#  if num_argument == 1:
#    ShowUsage()
#    return
#  elif num_argument == 2:
#    webm_file = webmFile(sys.argv[1])
#    if webm_file._file == None:
#      return
#    file_ = webm_file.GetFile()
#
#    ebml = Ebml()
#    ebml.ProcessEbml(file_, 0, True)
#    pos = ebml.GetFilePosition()
#    segment = Segment()
#    segment.SearchLevelOneElements(file_, pos)
#
#    while menu != '9':
#      menu = ShowMenu()
#      if menu == '1': # EBML
#        ebml.ProcessEbml(file_)
#      elif menu == '2': #SeekHead
#        segment.ProcessElement(file_, SEEKHEAD, 0)
#      elif menu == '3': #SegmentInfo
#        segment.ProcessElement(file_, SEGMENT_INFO, 0)
#      elif menu == '4': #Tracks
#        segment.ProcessElement(file_, TRACKS, 0)
#      elif menu == '5': #Cues
#        segment.ProcessElement(file_, CUES, 0)
#      elif menu == '6': #Clusters
#        i = 0
#        for cluster in segment._elements:
#          if int(cluster[0], 16) == CLUSTER:
#            segment.ProcessElement(file_, CLUSTER, i)
#            i = i + 1
#      elif menu == '7': #Capture
#        ebml.ProcessEbml(file_)
#        segment.ProcessElement(file_, SEEKHEAD, 0)
#        segment.ProcessElement(file_, SEGMENT_INFO, 0)
#        segment.ProcessElement(file_, TRACKS, 0)
#        segment.ProcessElement(file_, CUES, 0)
#
#        i = 0
#        for cluster in segment._elements:
#          if int(cluster[0], 16) == CLUSTER:
#            segment.ProcessElement(file_, CLUSTER, i)
#            i = i + 1
#  else:
#    print '\t\t Only need a WebM or Mkv filename. Too many arguments.'
#    return

  if num_argument == 1:
    print '\t\t * WebM Inspector %s' % GetVersion()
    print '\t\t  -. This command line tool dumps all info from a webm file.'
    print '\t\t  -. usage: python webminspector.py [webm file]'
    print '\t\t  -. ex: python webminspector.py sample.webm\n'
    sys.exit(1)

  webm_file = webmFile(sys.argv[1])
  if webm_file._file == None:
    return
  file_ = webm_file.GetFile()

  try:
    ebml = Ebml()
    ebml.ProcessEbml(file_, 0, True)
    pos = ebml.GetFilePosition()
    segment = Segment()
    size, start_pos = ReadOneByteForElementIdSize(file_, pos)
    element_id, pos = ProcessIdSize(file_, start_pos, size)
    data_size_length, pos = ReadOneByteForDataSize(file_, pos)
    data_size, pos = ProcessDataSize(file_, pos, data_size_length)
    segment.SetTotalSizeSegment(data_size)
    while pos <= data_size:
      pos = segment.SearchLevelOneElements(file_, pos)
    ebml.ProcessEbml(file_)
    segment.ProcessElement(file_, SEEKHEAD, 0)
    segment.ProcessElement(file_, SEGMENT_INFO, 0)
    segment.ProcessElement(file_, TRACKS, 0)
    segment.ProcessElement(file_, CUES, 0)

    i = 0
    for cluster in segment._elements:
      if int(cluster[0], 16) == CLUSTER:
        segment.ProcessElement(file_, CLUSTER, i)
        i += 1

  except KeyboardInterrupt:
    file_.close()

  return

if __name__ == "__main__":
  main()
