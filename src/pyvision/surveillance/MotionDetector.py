'''
Created on Nov 9, 2010
@author: svohara
'''
# PyVision License
#
# Copyright (c) 2006-2008 Stephen O'Hara
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
# 
# 3. Neither name of copyright holders nor the names of its contributors
# may be used to endorse or promote products derived from this software
# without specific prior written permission.
# 
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import pyvision as pv
from pyvision.surveillance.BackgroundSubtraction import *
import cv

class MotionDetector(object):
    '''
    Uses background subtraction from an image buffer to detect
    areas of motion in a video.
    
    The general process is to update the image buffer and then
    call the MotionDetector's detect() method.
    '''
    
    def __init__(self, imageBuff, thresh=20, method=BG_SUBTRACT_FD, minArea=400, rectFilter=None):
        '''
        Constructor
        @param imageBuff: a pv.ImageBuffer object, already full, to be used
          in the background subtraction step of the motion detection.
        @param thresh: Used by the background subtraction to eliminate noise.  
        @param method: Select background subtraction method. See constants defined in
          BackgroundSubtraction module
        @param minArea: minimum foreground contour area required for detection
        @param rectFilter: a function reference that takes a list of rectangles and
          returns a list filtered in some way. This allows the user to arbitrarily
          define rules to further limit motion detection results based on the geometry
          of the bounding boxes.
        '''
        #initialize object variables
        self._fgMask = None        
        self._minArea = minArea
        self._filter = rectFilter
        self._imageBuff = imageBuff
        self._method = method
        
        if method==BG_SUBTRACT_FD:
            self._bgSubtract = pv.FrameDifferencer(imageBuff, thresh)
            self._annotateImg = imageBuff.getMiddle()
        elif method==BG_SUBTRACT_MF:
            self._bgSubtract = pv.MedianFilter(imageBuff, thresh)
            self._annotateImg = imageBuff.getLast()
        elif method==BG_SUBTRACT_AMF:
            self._bgSubtract = pv.ApproximateMedianFilter(imageBuff, thresh)
            self._annotateImg = imageBuff.getLast()
        else:
            raise ValueError("Unknown Background Subtraction Method specified.")
        
    def detect(self):
        '''
        After an image has been added to the image buffer, you call this method
        to update detection results. After updating detection results, use one
        of the getX() methods, such as getRects() to see the results in the
        appropriate format.
        '''
        
        mask = self._bgSubtract.getForegroundMask()
        cvBinary = mask.asOpenCVBW()
        cv.Dilate(cvBinary, cvBinary, None, 3)
        cv.Erode(cvBinary, cvBinary, None, 1)
        
        #update the foreground mask
        self._fgMask = pv.Image(cvBinary)
        
        #update the detected foreground contours
        self._computeContours()
        
        #update current annotation image from buffer, as appropriate for
        # the different methods
        if self._method==BG_SUBTRACT_FD:
            self._annotateImg = self._imageBuff.getMiddle()
        elif self._method==BG_SUBTRACT_MF:
            self._annotateImg = self._imageBuff.getLast()
        elif self._method==BG_SUBTRACT_AMF:
            self._annotateImg = self._imageBuff.getLast()
       
    def _computeContours(self):
        cvMask = self._fgMask.asOpenCVBW()
        cvdst = cv.CloneImage(cvMask)  #because cv.FindContours may alter source image
        contours = cv.FindContours(cvdst, cv.CreateMemStorage(), cv.CV_RETR_EXTERNAL, cv.CV_CHAIN_APPROX_SIMPLE)
        self._contours = contours
        
    def getForegroundMask(self):
        '''
        @return: a binary pv.Image representing the foreground pixels
        as determined by the selected background subtraction method.
        @note: You must call the detect() method before getForegroundMask() to
        get the updated mask.
        '''
        return self._fgMask
            
    def getRects(self):
        '''
        @return: the bounding boxes of the external contours of the foreground mask.
        @note: You must call detect() before getRects() to see updated results.
        '''
        #create a list of the top-level contours found in the contours (cv.Seq) structure
        rects = []
        if len(self._contours) < 1: return(rects)
        seq = self._contours
        while not (seq == None):
            (x, y, w, h) = cv.BoundingRect(seq) 
            if (cv.ContourArea(seq) > self._minArea):
                r = pv.Rect(x,y,w,h)
                rects.append(r)
            seq = seq.h_next()
        
        if self._filter != None:
            rects = self._filter(rects)
        
        return rects
    
    def getAnnotatedImage(self, showContours=False):
        '''
        @return: the annotation image with bounding boxes
        and optionally contours drawn upon it.
        @note: You must call detect() prior to getAnnotatedImage()
        to see updated results.
        '''
        rects = self.getRects()
        outImg = self._annotateImg.copy()  #deep copy, so can freely modify the copy
        
        #draw contours in green
        if showContours:
            cvimg = outImg.asOpenCV()
            cv.DrawContours(cvimg, self._contours, cv.RGB(0, 255, 0), cv.RGB(255,0,0), 2)
        
        #draw bounding box in yellow
        for r in rects:
            outImg.annotateRect(r,"yellow")
        
        return outImg        
        
    def getForegroundTiles(self):
        '''
        @return: a list of "tiles", where each tile is a small pv.Image
        representing the clipped area of the annotationImg based on
        the motion detection. The foreground mask will be used to show
        only the foreground pixels within each tile.
        @note: You must call detect() prior to getForegroundTiles() to get
        updated information.
        '''
        cvMask = self._fgMask.asOpenCVBW()
        cvImg = self._annotateImg
        return None