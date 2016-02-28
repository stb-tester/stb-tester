##
##  Copyright (c) 2010 The WebM project authors. All Rights Reserved.
##
##  Use of this source code is governed by a BSD-style license
##  that can be found in the LICENSE file in the root of the source
##  tree. An additional intellectual property rights grant can be found
##  in the file PATENTS.  All contributing project authors may
##  be found in the AUTHORS file in the root of the source tree.
##

__author__ = 'hwasoolee@google.com (Hwasoo Lee)'

import sys
import struct
from ebml_header import *

def GetVersion():
  """Return this module version
  """
  return 'v0.9.3'

def BitSet(x, n):
  """Return whether nth bit of x was set"""
  return bool(x[0] & (1 << n))

def ConvertStrNumber(input):
  size = len(input)
  index = 0
  value = 0
  total = 0
  while size != index:
    value = eval(str(input[index])) << (8*(size-(index+1)))
    total = value + total
    index += 1

  return total

def InterpretLittleEndian(data, i):
  temp_data = 0
  while (i):
    temp_data += data[i-1] << 8 * (i - 1)
    i -= 1

  return temp_data

def CalculatePacketBlockSize(data):
  block_size_0 = data & 0x0F
  block_size_1 = data & 0xF0
  block_size_1 = block_size_1 >> 4
  return block_size_0, block_size_1

def ReadOneByteForElementIdSize(file_, pos):
  file_.seek(pos)
  ch = file_.read(1)
  pre_id = struct.unpack('>B', ch)
  pos = file_.tell()
  pos = pos - 1

  if (pre_id[0] & 0x80):   # 1000 0000
    size_to_read = 1
  elif (pre_id[0] & 0x40): # 0100 0000
    size_to_read = 2
  elif (pre_id[0] & 0x20): # 0010 0000
    size_to_read = 3
  elif (pre_id[0] & 0x10): # 0001 0000
    size_to_read = 4
  else:
    assert 0, 'ReadOneByteForElementIdSize Error'

  return size_to_read, pos

def ReadOneByteForDataSize(file_, pos):
  """
  This is to read data size field which is the second field followed by Element
  Id field. Do not confuse with Data field itself.
  """
  file_.seek(pos)
  ch = file_.read(1)
  pre_data = struct.unpack('>B', ch)
  pos = file_.tell()
  pos = pos - 1

  if   (pre_data[0] & 0x80): #
    data_size = 1
  elif (pre_data[0] & 0x40): #
    data_size = 2
  elif (pre_data[0] & 0x20): #
    data_size = 3
  elif (pre_data[0] & 0x10): #
    data_size = 4
  elif (pre_data[0] & 0x08): #
    data_size = 5
  elif (pre_data[0] & 0x04): #
    data_size = 6
  elif (pre_data[0] & 0x02): #
    data_size = 7
  elif (pre_data[0] & 0x01): #
    data_size = 8
  else:
    data_size = 0

  assert data_size  > 0
  return data_size, pos

def ReadClassId(file_, pos, bytes, unpack_mode):
  file_.seek(pos)
  data = file_.read(bytes)
  pos = file_.tell()
  class_id = struct.unpack(unpack_mode, data)
  format = 'hex(class_id[%s])+'
  format = format*bytes
  length = format % tuple(range(0,bytes))
  length = length[:-1]
  classid = eval(length)
  classid = classid[2:].replace('0x','')
  return classid, pos

def ProcessIdSize(file_, pos, size):
  id_size, pos = ReadClassId(file_, pos, size, '>%dB' % size)
  return id_size, pos

def ReadDataSize(file_, pos, bytes_read, unpack_mode):
  file_.seek(pos)
  data = file_.read(bytes_read)

  pos = file_.tell()
  data_size = struct.unpack(unpack_mode, data)

  if   (data_size[0] & 0x80):
    data_size_0 = data_size[0] & 0x7F
  elif (data_size[0] & 0x40): #
    data_size_0 = data_size[0] & 0x3F
  elif (data_size[0] & 0x20): #
    data_size_0 = data_size[0] & 0x1F
  elif (data_size[0] & 0x10): #
    data_size_0 = data_size[0] & 0x08
  elif (data_size[0] & 0x08): #
    data_size_0 = data_size[0] & 0x07
  elif (data_size[0] & 0x04): #
    data_size_0 = data_size[0] & 0x03
  elif (data_size[0] & 0x02): #
    data_size_0 = data_size[0] & 0x01
  else: #
    data_size_0 = 0 # TODO: research in which case this statement is executed.

  len_  = len(data_size)
  #print 'data_size %s' % data_size
  total_data_size = 0
  if bytes_read == 1:
    total_data_size = data_size_0
  else:
    index = 1
    value = 0
    total_data_size = data_size_0 << (8 * (len_ - 1))
    while len_ != index:
      value = eval(str(data_size[index])) << (8 * (len_ - (index + 1)))
      total_data_size = value + total_data_size
      index = index + 1

  return total_data_size, pos

def ProcessDataSize(file_, pos, data_size_length):
  data_size, pos = ReadDataSize(file_, pos, data_size_length, '>%dB' % data_size_length)
  return data_size, pos

def ProcessData(file_, pos, data_size, option):
  file_.seek(pos)
  data = file_.read(data_size)
  pos = file_.tell()

  if option == EBML_FLOAT: # u-integer
    if len(data) == 4:
      data_ = struct.unpack('>f', data)
    if len(data) == 8:
      data_ = struct.unpack('>d', data)
  elif option == EBML_UINTEGER: # u-integer
    data_ = struct.unpack('>%dB' % data_size, data)
  elif option == EBML_STRING or option == EBML_UTF8:   # string
    data_ = struct.unpack('>%ds' % data_size, data)
  elif option == EBML_BINARY:   # binary
    data_ = struct.unpack('>%dB' % data_size, data)
  elif option == EBML_DATE:   # date
    data_ = struct.unpack('>%dB' % data_size, data)
  else:
    assert 0, 'Data Handling Error'
    exit(1)

  return data_, pos

def HandleData(self, dic, Process, file_, pos, ebml_head_flag = False):
  start_pos = pos
  size, pos = ReadOneByteForElementIdSize(file_, pos)
  element_id, pos = ProcessIdSize(file_, pos, size)
 # TODO(hwasoo): need to check element id

  data_size_length, pos = ReadOneByteForDataSize(file_, pos)
  assert data_size_length > 0

  data_size, pos = ProcessDataSize(file_, pos, data_size_length)

  if int(element_id, 16)  in dic.keys():
    if dic[int(element_id, 16)][2] == EBML_SUB_ELEMENT:
      self._total_size_to_read = data_size + pos
      if ebml_head_flag == False:
        print '\t\t' + str(dic[int(element_id, 16)][0])\
            + ' (head size: ' + repr(size + data_size_length)\
            + ' bytes, data: ' + repr(data_size) +' bytes, pos: '\
            + repr(start_pos) + ', ' + repr(hex(start_pos)) + ')'
    else:
      data_, pos = ProcessData(file_, pos, data_size, dic[int(element_id, 16)][2])
      if len(data_) != 1:
        data_value = ConvertStrNumber(data_)
        if data_value == SEGMENT_INFO:
          output = 'SegmentInfo'
        elif data_value == TRACKS:
          output = 'Tracks'
        elif data_value == CUES:
          output = 'Cues'
        elif data_value == SEEKHEAD:
          output = 'SeekHead'
        elif data_value == CLUSTER:
          output = 'cluster'
        else:
          output = data_value
      else:
        output = data_[0]

      if ebml_head_flag == False:
        print '\t\t\t' + str(dic[int(element_id, 16)][0]) \
            + ' (head size: ' + repr(size + data_size_length) \
            + ' bytes, data: ' + repr(data_size) +' bytes, pos: '\
            + repr(start_pos) +  ', ' + repr(hex(start_pos)) +  ') : ' + repr(output)

      if self._total_size_to_read <= pos:
        self._file_pos = pos
        return

  Process(file_, pos, ebml_head_flag)

def RenderElement(self, file_, element_id):
  for eid in self._elements:
    if int(eid[0], 16) == element_id:
      print 'Found %s' % element_id
    else:
      print 'Not Found'

def CalculatePacketSize(data, i):
  loop = 0

  while (data[i] == 255):
    i +=  1
    loop +=  1

  return 255 * loop + data[i], (lambda  x: x + 1)(i)


def DisplayVP8Data(data):
  # for now we just handle simple block with no lacing data case
  keyframe = BitSet(data[4:5], 0)
  version = data[4] & 0x0E
  showframe = BitSet(data[4:5], 4)

  first_data_partition = InterpretLittleEndian(data[4:7], 3) >> 5

  if keyframe == False:
    k_o = 'Yes'
  else:
    k_o = 'No'

  if showframe == True:
    s_o = 'Yes'
  else:
    s_o = 'No'

  output = '[VP8] key: %s, ver: %d, sf: %s, pl: %d' % \
     (k_o, version, s_o, first_data_partition)

  return output


def DisplayCodecPrivateData(data, total):
  print '\t\t\t\tNumber of packets : %d' % (data[0] + 1)

  size_1, i = CalculatePacketSize(data, 1)
  print '\t\t\t\tFirst packet size : %d byte(s)' % size_1

  size_2, i = CalculatePacketSize(data, i)
  print '\t\t\t\tSecond packet size : %d byte(s)' % size_2

  print '\t\t\t\tThird packet size : %d bytes(s)' % (total - i - size_1 - size_2)

  if (data[i] == 1):
    print '\t\t\t\t   [Identification Header]'
    if (data[i+1] == 118) & \
       (data[i+2] == 111) & \
       (data[i+3] == 114) & \
       (data[i+4] ==  98) & \
       (data[i+5] == 105) & \
       (data[i+6] == 115):
      print '\t\t\t\t\tvorbis'
    else:
      print '\t\t\t\t\tnot valid to vorbis'
    i += 6 #skip to vorbis version location

    if (data[i+1] == 0) & \
       (data[i+2] == 0) & \
       (data[i+3] == 0) & \
       (data[i+4] == 0):
      print '\t\t\t\t\tVorbis version : 0'
    else:
      print '\t\t\t\t\tVorbis version : non-0'
    i += 4

    #audio channel
    print '\t\t\t\t\tAudio channel : %d ' % data[i+1]
    i += 1

    sampling_rate = [data[i+1], data[i+2], data[i+3], data[i+4]]
    print '\t\t\t\t\tSampling rate : %d ' % InterpretLittleEndian(sampling_rate, 4)
    i += 4

    bitrate_maximum = [data[i+1], data[i+2], data[i+3], data[i+4]]
    print '\t\t\t\t\tBitrate maximum : %d ' % InterpretLittleEndian(bitrate_maximum, 4)
    i += 4
    bitrate_nominal = [data[i+1], data[i+2], data[i+3], data[i+4]]
    print '\t\t\t\t\tBitrate nominal : %d ' % InterpretLittleEndian(bitrate_nominal, 4)
    i += 4
    bitrate_minimum = [data[i+1], data[i+2], data[i+3], data[i+4]]
    print '\t\t\t\t\tBitrate minimum : %d ' % InterpretLittleEndian(bitrate_minimum, 4)
    i += 4

    block_size_0, block_size_1 = CalculatePacketBlockSize(data[i+1])
    print '\t\t\t\t\tBlock Size 0 : %d ' %  (1 << block_size_0)
    print '\t\t\t\t\tBlock Size 1 : %d ' %  (1 << block_size_1)
    i += 1

    print '\t\t\t\t\tFraming Flag : %d' % bool(data[i+1])
    i += 1

  i += 1
  if (data[i] == 3):
    print '\t\t\t\t   [Comment Header]'
    if (data[i+1] == 118) & \
       (data[i+2] == 111) & \
       (data[i+3] == 114) & \
       (data[i+4] ==  98) & \
       (data[i+5] == 105) & \
       (data[i+6] == 115):
      print '\t\t\t\t\tvorbis'
    else:
      print '\t\t\t\t\tnot valid to vorbis'
    i += 6 #skip to vorbis version location

    vendor_length = [data[i+1], data[i+2], data[i+3], data[i+4]]
    v_l =  InterpretLittleEndian(vendor_length, 4)
    print '\t\t\t\t\tVendor Length : %d ' % v_l
    i += 4

    i += 1
    vendor_string = data[i:i+v_l]
    print '\t\t\t\t\tVendor string : ' + ''.join(map(chr, vendor_string))

    i += v_l
    ucll = [data[i], data[i+1], data[i+2], data[i+3]]
    user_comment_list_length = InterpretLittleEndian(ucll, 4)

    i += 4
    while user_comment_list_length > 0:
      temp = [data[i], data[i+1], data[i+2], data[i+3]]
      temp_num = InterpretLittleEndian(temp, 4)
      i += 4
      user_comment = data[i:i+temp_num]
      print '\t\t\t\t\tComment : '
      print '\t\t\t\t\t\t '+''.join(map(chr, user_comment))
      i += temp_num
      user_comment_list_length -= 1

    print '\t\t\t\t\tFraming Flag : %d' % bool(data[i+1])
    i += 1

  return

  #TODO: Codec setup header
  #This task is comprehensive and nontrivial since the knowledge of Vorbis
  #specification is needed.
  if (data[i] == 5):
    print '\t\t\t\t   [Setup Header]'
    if (data[i+1] == 118) & \
       (data[i+2] == 111) & \
       (data[i+3] == 114) & \
       (data[i+4] ==  98) & \
       (data[i+5] == 105) & \
       (data[i+6] == 115):
      print '\t\t\t\t\tvorbis'
    else:
      print '\t\t\t\t\tnot valid to vorbis'
    i += 6 #skip to vorbis version location

    i += 1
    vorbis_codebook_count = data[i] + 1
    print '\t\t\t\t\tvorbis_codebook_count : %d' % vorbis_codebook_count
    if (data[i+1] == 66) & \
       (data[i+2] == 67) & \
       (data[i+3] == 86):
      print '\t\t\t\t\tcodebook begin : 0x564342'
    else:
      print '\t\t\t\t\tnot valid codebook begins'

    i += 3

    i += 1
    codebook_dimensions = InterpretLittleEndian(data[i:i+2], 2)
    print '\t\t\t\t\tcodebook_dimensions : %d' % codebook_dimensions

    i += 2

    codebook_entries = InterpretLittleEndian(data[i:i+3], 3)
    print '\t\t\t\t\tcodebook_entries : %d ' % codebook_entries

    i += 3

    ordered_bit_flag = BitSet(data[i:i+1], 0)

    print '\t\t\t\t\torder bit flag : %d' % ordered_bit_flag
    if ordered_bit_flag:
      corrent_entry = 0
      current_length = data[i:i+1] & 0x7C # 0111 1100
      print current_lenth
    else:
      sparse_bit_flag = BitSet(data[i:i+1], 1)
      print '\t\t\t\t\tSparse bit flag : %d' % sparse_bit_flag

      if sparse_bit_flag:
        flag = BitSet(data[i:i+1], 2)
      else:
        length = InterpretLittleEndian(data[i:i+1], 1)
        length = length & 0x7C # 0111 1100

        print '\t\t\t\t\tlength : %d ' % ((length >> 2) + 1)

class webmFile:
  def __init__(self, filename):
    try:
      self._file = open(filename,'rb')
    except IOError:
      print ' No such file or directory : %s' % filename
      self._file = None

  def GetFile(self):
    return self._file

class Ebml:
  def __init__(self):
    self._ebml_data =    {
      EBML : ('EBML', LEVEL_0, EBML_SUB_ELEMENT),
      EBML_VERSION  : ('EBMLVersion', LEVEL_1, EBML_UINTEGER),
      EBML_READ_VERSION : ('EBMLReadVersion', LEVEL_1, EBML_UINTEGER),
      EBML_MAX_ID_LENGTH : ('EBMLMaxIDLength', LEVEL_1, EBML_UINTEGER),
      EBML_MAX_SIZE_LENGTH : ('EBMLMaxSizeLength', LEVEL_1, EBML_UINTEGER),
      EBML_DOC_TYPE : ('DocType', LEVEL_1, EBML_STRING),
      EBML_DOC_TYPE_VERSION : ('DocTypeVersion', LEVEL_1, EBML_UINTEGER),
      EBML_DOC_TYPE_READ_VERSION : ('DocTypeReadVersion', LEVEL_1, EBML_UINTEGER),
      VOID : ('Void', LEVEL_1, EBML_BINARY)
    }
    self._total_size_to_read = 0
    self._file_pos = 0

  def ProcessEbml(self, file_, pos = 0, ebml_head_flag = False):
    HandleData(self, self._ebml_data, self.ProcessEbml, file_, pos,
               ebml_head_flag)
    #    #TODO:
    #    # When trying to return pos value, it turns to None with some reason.
    #    # I do not know why. So I make the GetFilePosition()
    #    # Got to spend time to understand this.

  def GetFilePosition(self):
    return self._file_pos

class Segment:
  def __init__(self):
    self._segment_data  = {
      CRC_32 : ('Crc-32', LEVEL_1, EBML_BINARY),
      VOID : ('Void', LEVEL_1, EBML_BINARY),
      SEGMENT : ('Segment', LEVEL_0, EBML_SUB_ELEMENT),
      SEEKHEAD : ('SeekHead', LEVEL_1, EBML_SUB_ELEMENT),
      SEEK : ('Seek', LEVEL_2, EBML_SUB_ELEMENT),
      SEEKID : ('SeekID', LEVEL_3, EBML_BINARY),
      SEEKPOSITION : ('SeekPosition', LEVEL_3, EBML_UINTEGER),
      SEGMENT_INFO : ('SegmentInfo', LEVEL_1, EBML_SUB_ELEMENT),
      CLUSTER : ('Cluster', LEVEL_1, EBML_SUB_ELEMENT),
      TRACKS : ('Tracks', LEVEL_1, EBML_SUB_ELEMENT),
      VIDEO : ('Video', LEVEL_3, EBML_SUB_ELEMENT),
      AUDIO : ('Audio', LEVEL_3, EBML_SUB_ELEMENT),
      CUES : ('Cues', LEVEL_1, EBML_SUB_ELEMENT),
      ATTACHMENTS : ('Attachments', LEVEL_1, EBML_SUB_ELEMENT),
      CHAPTERS : ('Chapters', LEVEL_1, EBML_SUB_ELEMENT),
      TAGS : ('Tags', LEVEL_1, EBML_SUB_ELEMENT)
    }
    self._total_size_to_read = 0
    self._seeks = []
    self._elements = []
    self._total_size_for_segment = 0
    self._start_pos = 0
    self._track_number_type = [-1, -1, -1, -1]
    self._flag_track_done = False

  """
  Search Ebml element head in a segment
  """
  def Find(self, file_, Id):
    loop = 0
    while len(self._seeks) != 0:
      s = self._seeks[loop]
      pos = s.pos_
      size, pos = ReadOneByteForElementIdSize(file_, pos)
      element_id, pos = ProcessIdSize(file_, pos, size)
      data_size_length, pos = ReadOneByteForDataSize(file_, pos)
      assert data_size_length > 0

      data_size, pos = ProcessDataSize(file_, pos, data_size_length)
      data_, pos = ProcessData(file_, pos, data_size, EBML_UINTEGER)
      number = ConvertStrNumber(data_)

      if number == Id:
        size, pos = ReadOneByteForElementIdSize(file_, pos)
        element_id, pos = ProcessIdSize(file_, pos, size)
        data_size_length, pos = ReadOneByteForDataSize(file_, pos)
        assert data_size_length > 0
        data_size, pos = ProcessDataSize(file_, pos, data_size_length)
        data_, pos = ProcessData(file_, pos, data_size, EBML_UINTEGER)
        total = ConvertStrNumber(data_)
        return total + self._seekhead_pos

      loop =  loop + 1
      if len(self._seeks) == loop:
        return -1

  def GetSeekHeadPos(self):
    return self._seekhead_pos

  def GetSeekHeadSize(self):
    return self._seekhead_size

  def GetSeekElement(self):
    return self._seeks

  def GetTotalSizeSegment(self):
    return self._total_size_for_segment

  def SetTotalSizeSegment(self, size):
    self._total_size_for_segment = size

  def SearchLevelOneElements(self, file_, pos):
    """
    Search Level One Ebml Elements and put in a list
    """
    if pos > self._total_size_for_segment and self._total_size_for_segment != 0:
      return

    size, start_pos = ReadOneByteForElementIdSize(file_, pos)
    element_id, pos = ProcessIdSize(file_, start_pos, size)

    if pos > self._total_size_for_segment and self._total_size_for_segment != 0:
      return

    data_size_length, pos = ReadOneByteForDataSize(file_, pos)
    assert data_size_length > 0

    if pos > self._total_size_for_segment and self._total_size_for_segment != 0:
      return

    data_size, pos = ProcessDataSize(file_, pos, data_size_length)

    if pos > self._total_size_for_segment and self._total_size_for_segment != 0:
      return

    if int(element_id, 16)  ==  SEGMENT:
      self._total_size_for_segment = data_size
    elif int(element_id, 16) in self._segment_data.keys():
      head_size = size + data_size_length
      #make them tuple
      item = (element_id, start_pos, data_size, head_size)
      #add a tuple data in the list
      self._elements.append(item)
      #self._elements.append(start_pos)
    else:
      assert False

    if pos <= self._total_size_for_segment:
      if int(element_id, 16) == SEGMENT:
        self.SearchLevelOneElements(file_, pos)
      else:
        next_pos = data_size + start_pos + size + data_size_length
        return next_pos
        #self.SearchLevelOneElements(file_, next_pos)

  def ProcessSegment(self, file_, pos):
    HandleData(self, self._segment_data, self.ProcessSegment, file_, pos)

  #to know how many Seeks are there in Seekhead
  def EnumerateElement(self, file_, size_, pos):
    stop = size_ + pos

    while stop >= pos:
      size, pos = ReadOneByteForElementIdSize(file_, pos)
      element_id, pos = ProcessIdSize(file_, pos, size)
      data_size_length, pos = ReadOneByteForDataSize(file_, pos)
      assert data_size_length > 0

      data_size, pos = ProcessDataSize(file_, pos, data_size_length)
      if int(element_id, 16)  == SEEK: #0x4DBB
        s = Seek(pos, data_size)
        self._seeks.append(s)
        pos = pos + data_size

      #if id  == TRACK_ENTRY: #0xAE
      #  s = Seek(pos, data_size)
      #  self._seeks.append(s)
      #  pos = pos + data_size

      if id == VIDEO:
        print "Video"

      if id == AUDIO:
        print "Audio"

  def ProcessElement(self, file_, element_id_, index):
    i = 0
    time_code_absolute = 0
    loop = 0

    for eid in self._elements:
      if int(eid[0], 16) == element_id_:
        if i == index:
          stop = eid[1] + eid[2] + eid[3]
          start_pos = pos = eid[1]
          flag_sub_element = False

          while stop >= pos:
            size, pos = ReadOneByteForElementIdSize(file_, pos)
            pos_sub_element = pos
            element_id, pos = ProcessIdSize(file_, pos, size)

            data_size_length, pos = ReadOneByteForDataSize(file_, pos)
            assert data_size_length > 0

            data_size, pos = ProcessDataSize(file_, pos, data_size_length)
            pos_binary = pos # saving for Cluster

            for dic_ in dic_element:
              if dic_ == element_id_:
                handle_dic = dic_element[dic_]

            if int(element_id, 16) in handle_dic.keys():
              if handle_dic[int(element_id, 16)][2] == EBML_SUB_ELEMENT:
                self._total_size_to_read = data_size + pos
                if flag_sub_element == True:
                  pos_display = pos_sub_element
                else:
                  pos_display = start_pos

                print '\t\t' + str(handle_dic[int(element_id, 16)][0])\
                    + ' (head size: ' + repr(size + data_size_length)\
                    + ' bytes, data: ' + repr(data_size) +' bytes, pos: '\
                    + repr(pos_display) + ', ' + repr(hex(pos_display)) + ')'
                flag_sub_element = True
              else:
                flag_sub_element = False
                data_, pos = ProcessData(file_, pos, data_size, handle_dic[int(element_id, 16)][2])
                flag_simple_block = False
                key_frame = False
                lacing = 'no lacing'
                invisible = 'no'
                discardable = 'no'

                flag_codec_private = False;

                if handle_dic[int(element_id, 16)][2] == EBML_BINARY:
                  if SIMPLE_BLOCK in handle_dic:
                    track_number, pos_temp = ProcessDataSize(file_, pos_binary, 1)
                    time_code, pos_temp = ProcessData(file_, pos_temp, 2,
                                                      EBML_UINTEGER)
                    time_offset = (time_code[0] << 8) + time_code[1]

                    #Block header - offset+3
                    file_.seek(pos_temp)
                    lacing_data = file_.read(1)
                    offset_three_data = struct.unpack('>B', lacing_data)
                    #print 'BitSet Test : ' + repr(BitSet(offset_three_data, 7))
                    key_frame = BitSet(offset_three_data, 7)

                    if BitSet(offset_three_data, 4):
                      invisible = 'yes'

                    if BitSet(offset_three_data, 0):
                      discardable = 'yes'

                    flag_lacing = offset_three_data[0] & 0x6
                    if flag_lacing == 0x2:
                      lacing = 'Xiph lacing'
                    elif flag_lacing == 0x4:
                      lacing = 'fixed-size lacing'
                    elif flag_lacing == 0x6:
                      lacing = 'EBML lacing'
                    else:
                      lacing = 'no lacing'

                    flag_simple_block = True

                    if self._flag_track_done and (self._track_number_type[0] ==\
                       self._track_number_type[1]) and (track_number == 1):
                      output = DisplayVP8Data(data_)
                    else:
                      output = 'binary'

                    #output = data_
                  elif CODEC_PRIVATE == int(element_id, 16):
                    #output = 'Codec Private'
                    output = data_
                    flag_codec_private = True
                    #DisplayCodecPrivateData(data_)
                  elif VOID == int(element_id, 16):
                    output = 'Void'
                  else:
                    data_value = ConvertStrNumber(data_)
                    if data_value == SEGMENT_INFO:
                      output = 'SegmentInfo'
                    elif data_value == TRACKS:
                      output = 'Tracks'
                    elif data_value == CUES:
                      output = 'Cues'
                    elif data_value == SEEKHEAD:
                      output = 'SeekHead'
                    elif data_value == CLUSTER:
                      output = 'Cluster'
                    else:
                      output = data_value
                elif len(data_) != 1:
                  data_value = ConvertStrNumber(data_)
                  output = data_value
                  if TIMECODE in handle_dic:
                    time_code_absolute = output
                else:
                  output = data_[0]

                if flag_codec_private:
                  print '\t\t\t' + str(handle_dic[int(element_id, 16)][0]) \
                     + ' (head size: ' + repr(size + data_size_length) \
                     + ' bytes, data: ' + repr(data_size) +' bytes, pos: '\
                     + repr(pos_sub_element) +  ', '\
                     + repr(hex(pos_sub_element)) +  ') : '
                  print '\t\t\t' + repr(DisplayCodecPrivateData(output, data_size))
                else:
                  if int(element_id, 16) == TRACK_TYPE:
                    self._track_number_type[loop] = output
                    loop += 1

                  if int(element_id, 16) == TRACK_NUMBER:
                    self._track_number_type[loop] = output
                    loop += 1

                  if loop == 4:
                    self._flag_track_done = True
                    loop = 0

                  print '\t\t\t' + str(handle_dic[int(element_id, 16)][0]) \
                     + ' (head size: ' + repr(size + data_size_length) \
                     + ' bytes, data: ' + repr(data_size) +' bytes, pos: '\
                     + repr(pos_sub_element) +  ', ' +\
                     repr(hex(pos_sub_element)) +  ') : ' + repr(output)

                if flag_simple_block == True:
                  print '\t\t\t  ' + 'track number : ' + repr(track_number) \
                                   + ', keyframe : ' + repr(key_frame) \
                                   + ', invisible : ' + repr(invisible) \
                                   + ', discardable : ' + repr(discardable)
                  print '\t\t\t  lace : ' + repr(lacing) \
                                   + ', time code : ' + repr(time_offset) \
                                   + ', time code(absolute) : ' \
                                   + repr(time_offset + time_code_absolute)

                if stop <= pos:
                  self._file_pos = pos
                  return
            else:
              print '\n\t\t>>>Seems invalid WebM file format<<<'
              print '\t\t at element code [%s]' % element_id 
              exit(1)
        else:
          i = i + 1

class SeekHead:
  def __init__(self):
    self._seek_head = {
      SEEKHEAD : ('SeekHead', LEVEL_1, EBML_SUB_ELEMENT),
      SEEK : ('Seek', LEVEL_1, EBML_SUB_ELEMENT),
      SEEKID : ('SeekId', LEVEL_2, EBML_BINARY),
      SEEKPOSITION : ('SeekPosition', LEVEL_3, EBML_UINTEGER)
    }

  def ProcessSeekHead(self, file_, pos):
    HandleData(self, self._seek_head, self.ProcessSeekHead, file_, pos)

class Seek:
  def __init__(self, pos, stop):
    self._seek = {
      SEEKID : ('SeekId', LEVEL_2, EBML_BINARY),
      SEEKPOSITION : ('SeekPosition', LEVEL_3, EBML_UINTEGER)
    }
    self._total_size_to_read = stop + pos
    self.pos_ =  pos

  def ProcessSeek(self, file_, pos):
    HandleData(self, self._seek, self.ProcessSeek, file_, pos)

def ShowUsage():
  print '\t\t\t WebM inspector v0.1'
  print '\t\t\t   python webminspector.py [webm file]'
  print '\t\t\t   ex) python webminspector.py test.webm'

def ShowMenu():
  print '\t\t Please choose a menu'
  print '\t\t  1. show EBML'
  print '\t\t  2. show SeekHead'
  print '\t\t  3. show SegmentInfo'
  print '\t\t  4. show Tracks'
  print '\t\t  5. show Cues'
  print '\t\t  6. show Clusters'
  print '\t\t  7. show all'
  print '\t\t  8. capture all'
  print '\t\t  9. exit'
  menu = raw_input('\t\t ? : ')
  return menu
