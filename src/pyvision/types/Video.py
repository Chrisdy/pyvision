# PyVision License
#
# Copyright (c) 2006-2008 David S. Bolme
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

import opencv
import opencv.highgui
import time
import subprocess
import os
#import highgui

from pyvision.types.Image import Image
from pyvision.edge.canny import canny
from pyvision.analysis.ImageLog import ImageLog

import pyvision as pv
import opencv as cv

from scipy import weave

class Webcam:
    def __init__(self,camera_num=1,size=(640,480)):

        self.cv_capture = opencv.highgui.cvCreateCameraCapture( camera_num )        
        
        self.size = size
    
    def query(self):
        '''
        The returned image also include a field named orig_frame which returns 
        the original image returned before rescaling.
        
        @returns: the frame rescaled to a given size.
        '''
        frame = opencv.highgui.cvQueryFrame( self.cv_capture );
        im = Image(self.resize(frame))
        im.orig_frame = Image(frame)
        im.capture_time = time.time()
        return im
    
    def grab(self):
        return opencv.highgui.cvGrabFrame( self.cv_capture );
    
    def retrieve(self):
        '''
        The returned image also include a field named orig_frame which returns 
        the original image returned before rescaling.
        
        @returns: the frame rescaled to a given size.
        '''
        frame = opencv.highgui.cvRetrieveFrame( self.cv_capture );
        im = Image(self.resize(frame))
        im.orig_frame = Image(frame)
        return im
        
    def resize(self,frame):
        if self.size == None:
            return frame
        else:
            depth = frame.depth
            channels = frame.nChannels
            w,h = self.size
            resized = opencv.cvCreateImage( opencv.cvSize(w,h), depth, channels )
            opencv.cvResize( frame, resized, opencv.CV_INTER_NN )
            return resized

class Video:
    def __init__(self,filename,size=None):
        self.filename = filename
        self.cv_capture = opencv.highgui.cvCreateFileCapture( filename );
        self.size = size
        self.n_frames = opencv.highgui.cvGetCaptureProperty(self.cv_capture,opencv.highgui.CV_CAP_PROP_FRAME_COUNT)
        self.current_frame = 0
        
    def __del__(self):
        #opencv.highgui.cvReleaseCapture(self.cv_capture)
        

        # cvReleaseCapture interface does not work so use weave this may be fixed in release 1570
        # TODO: This should be removed when the opencv bug is fixed
        capture = self.cv_capture.__int__()
        weave.inline(
            '''
            CvCapture* tmp = (CvCapture*) capture;
            cvReleaseCapture(&tmp);
            ''',
            arg_names=['capture'],
            type_converters=weave.converters.blitz,
            include_dirs=['/usr/local/include'],
            headers=['<opencv/cv.h>','<opencv/highgui.h>'],
            library_dirs=['/usr/local/lib'],
            libraries=['cv','highgui']
        )

    def query(self):
        if self.current_frame >= self.n_frames:
            return None
        self.current_frame += 1
        frame = opencv.highgui.cvQueryFrame( self.cv_capture );
        return Image(self.resize(frame))
    
    def grab(self):
        return opencv.highgui.cvGrabFrame( self.cv_capture );
    
    def retrieve(self):
        frame = opencv.highgui.cvRetrieveFrame( self.cv_capture );
        return Image(self.resize(frame))
        
    def resize(self,frame):
        if self.size == None:
            return frame
        else:
            depth = frame.depth
            channels = frame.nChannels
            w,h = self.size
            resized = opencv.cvCreateImage( opencv.cvSize(w,h), depth, channels )
            opencv.cvResize( frame, resized, opencv.CV_INTER_LINEAR )
            return resized
    
    def __iter__(self):
        ''' Return an iterator for this video '''
        return Video(self.filename,self.size)
        
    def next(self):
        frame = self.query()
        if frame == None:
            raise StopIteration("End of video sequence")
        return frame
        
                
        
class FfmpegIn:
    # TODO: there may be a bug with the popen interface
    
    def __init__(self,filename,size=None,aspect=None,options=""):
        self.filename = filename
        self.size = size
        self.aspect = aspect
        
        # Open a pipe
        args = "/opt/local/bin/ffmpeg -i %s %s -f yuv4mpegpipe - "%(filename,options)
        #print args
        
        self.stdin, self.stdout, self.stderr = os.popen3(args)
        #popen = subprocess.Popen(args,executable="/opt/local/bin/ffmpeg")
        
        line = self.stdout.readline()
        print line
        #self.stdout.seek(0,os.SEEK_CUR)
        
        format,w,h,f,t1,aspect,t2,t3 = line.split()
        
        # I am not sure what all this means but I am checking it anyway
        assert format=='YUV4MPEG2'
        #assert t1=='Ip'
        assert t2=='C420mpeg2'
        assert t3=='XYSCSS=420MPEG2'

        # get the width and height
        assert w[0] == "W"
        assert h[0] == "H"
        
        self.w = int(w[1:])
        self.h = int(h[1:])
        
        # Create frame caches        
        if size == None and self.aspect != None:
            h = self.h
            w = int(round(self.aspect*h))
            size = (w,h)
            #print size
        
        self.size = size
        
        self.frame_y = cv.cvCreateImage( cv.cvSize(self.w,self.h), cv.IPL_DEPTH_8U, 1 )
        self.frame_u2 = cv.cvCreateImage( cv.cvSize(self.w/2,self.h/2), cv.IPL_DEPTH_8U, 1 )
        self.frame_v2 = cv.cvCreateImage( cv.cvSize(self.w/2,self.h/2), cv.IPL_DEPTH_8U, 1 )

        self.frame_u = cv.cvCreateImage( cv.cvSize(self.w,self.h), cv.IPL_DEPTH_8U, 1 )
        self.frame_v = cv.cvCreateImage( cv.cvSize(self.w,self.h), cv.IPL_DEPTH_8U, 1 )
        self.frame_col = cv.cvCreateImage( cv.cvSize(self.w,self.h), cv.IPL_DEPTH_8U, 3 )

        
        if self.size != None:
            w,h = self.size
            self.frame_resized = cv.cvCreateImage(cv.cvSize(w,h),cv.IPL_DEPTH_8U,3)

        
        
    def frame(self):
        line = self.stdout.readline()
        #print line
        #print self.w,self.h
        y = self.stdout.read(self.w*self.h)
        u = self.stdout.read(self.w*self.h/4)
        v = self.stdout.read(self.w*self.h/4)
        if len(y) < self.w*self.h:
            raise EOF
        
        self.frame_y.imageData=y
        self.frame_u2.imageData=u
        self.frame_v2.imageData=v

        cv.cvResize(self.frame_u2,self.frame_u)
        cv.cvResize(self.frame_v2,self.frame_v)
        
        cv.cvMerge(self.frame_y,self.frame_u,self.frame_v,None,self.frame_col)
        cv.cvCvtColor(self.frame_col,self.frame_col,cv.CV_YCrCb2RGB)
        
        out = self.frame_col
        
        if self.size != None:
            cv.cvResize(self.frame_col,self.frame_resized)
            out = self.frame_resized

        return pv.Image(self.frame_y),pv.Image(self.frame_u),pv.Image(self.frame_v),pv.Image(out)
        
