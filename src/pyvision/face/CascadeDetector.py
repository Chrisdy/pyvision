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

from opencv.cv import *
from opencv.highgui import *

import os
import os.path
import subprocess
import sys
import random
import tempfile
import unittest

import pyvision
from pyvision.types.Rect import Rect
from pyvision.analysis.face import EyesFile
from pyvision.types.Image import Image
from pyvision.analysis.FaceAnalysis.FaceDetectionTest import FaceDetectionTest
import pickle
from pyvision.optimize.GeneticAlgorithm import GeneticAlgorithm,ChoiceVariable
import time
from pyvision.analysis.Table import Table

class CascadeNotFound(Exception):
    pass
class HaarTrainingError(Exception):
    pass


DEFAULT_CASCADE=os.path.join(pyvision.__path__[0],"config","haarcascade_frontalface_alt.xml")
OPENCV_CASCADE=os.path.join(pyvision.__path__[0],"config","haarcascade_frontalface_alt.xml")
CELEB1_CASCADE=os.path.join(pyvision.__path__[0],"config","facedetector_celebdb1.xml")
CELEB2_CASCADE=os.path.join(pyvision.__path__[0],"config","facedetector_celebdb2.xml")

DEFAULT_NEGATIVE=os.path.join(pyvision.__path__[0],"data","nonface")

class CascadeDetector:
    ''' This class is a wrapper around the OpenCV cascade detectior. '''
    
    def __init__(self, cascade_name=DEFAULT_CASCADE,orig_size=None,min_size=(60,60), image_scale=1.3, haar_scale=1.2, min_neighbors=2, haar_flags=0):
        ''' Init the detector and create the cascade classifier '''

        self.cascade_name  = cascade_name
        self.min_size      = min_size
        self.image_scale   = image_scale
        self.haar_scale    = haar_scale
        self.min_neighbors = min_neighbors
        self.haar_flags    = haar_flags
        
        if cascade_name != None:
            if not os.path.isfile(cascade_name):
                raise CascadeNotFound("Could not find file: "+cascade_name)
            # Save data for later pickling
            if orig_size == None:
                orig_size = cvSize(1,1)
            else:
                orig_size = cvSize(orig_size[0],orig_size[1])
            
            self.cascade_data = open(cascade_name).read()
            self.cascade = cvLoadHaarClassifierCascade( cascade_name, orig_size )
            self.storage = cvCreateMemStorage(0)
            self.trained = True
        
        
    def __call__(self,im):
        ''' This function is the same as detect. '''
        return self.detect(im)
    
    def __getstate__(self):
        ''' Function required to save and load the state from pickel. '''
        state = {}
        
        for key,value in self.__dict__.iteritems():
            if key in ['cascade','storage']:
                continue
            
            state[key] = value

        return state
    
    def __setstate__(self,state):
        ''' Function required to save and load the state from pickel. '''
        # Modeled after SVM pickling
        
        for key,value in state.iteritems():
            self.__dict__[key] = value
            
        
        filename = tempfile.mktemp()
        open(filename,'w').write(self.cascade_data)
        self.cascade = cvLoadHaarClassifierCascade( filename, cvSize(1,1) )
        self.storage = cvCreateMemStorage(0)
        os.remove(filename)

    def _resizeImage(self, image, scale=None, size=None):
        ''' Resize an image by a scale or a size. Internal use only.'''
        if scale != None and type(scale) in (int,float):
            size = (int(image.width*scale),int(image.height*scale))
        elif size != None and type(size) in [list,tuple]:
            size = (int(size[0]),int(size[1]))
        else:
            pass
        depth = image.depth
        channels = image.nChannels
        resized = cvCreateImage( cvSize(size[0],size[1]), depth, channels )
        cvResize( image, resized, CV_INTER_LINEAR )
        return resized
        
    def detect(self, im):
        ''' Runs the cascade classifer on an image. '''
        image = im.asOpenCV()
        
        min_size = cvSize(self.min_size[0],self.min_size[1])
        
        # Create a resized gray scale image
        if image.nChannels == 3:
            gray = cvCreateImage( cvSize(image.width,image.height), image.depth, 1 )
            cvCvtColor( image, gray, CV_BGR2GRAY );
            image = gray
            
            
        image = self._resizeImage(image,self.image_scale)
    
        # Equalize the image
        cvEqualizeHist( image, image )
        
        # Detect faces
        cvClearMemStorage( self.storage )
        
        faces = cvHaarDetectObjects( image, self.cascade, self.storage,
                                 self.haar_scale, self.min_neighbors, self.haar_flags, min_size );
    
        # Transform and return the points
        result = []
        for r in faces:
            rect = Rect(r.x/self.image_scale, r.y/self.image_scale, r.width/self.image_scale, r.height/self.image_scale)
            result.append(rect)
            
        return result

def trainHaarClassifier(pos_rects, 
                        neg_images, 
                        tile_size=(20,20),
                        nneg=2000,
                        nstages=20,
                        mem = 1500,
                        maxtreesplits = 0,
                        mode='BASIC',
                        minhitrate=0.9990,
                        maxfalsealarm=0.50,
                        max_run_time=72*3600,
                        verbose=False
                        ):
    '''
    Train the detector.
    '''        
    # Create a directory for training.
    training_dir  = tempfile.mktemp()
    os.makedirs(training_dir, 0700)

    random_name = "haar_"
    for i in range(8):
        random_name += random.choice('abcdefghijklmnopqrstuvwxyz')
    cascade_name  = random_name+"_cascade"
    pos_name      = random_name+"_pos.txt"
    pos_vec_name  = random_name+"_pos.vec"
    neg_name      = random_name+"_neg.txt"
    
    # Add positives to the positives file.
    pos_filename = os.path.join(training_dir,pos_name)
    pos_file = open(pos_filename,'w')
    num_pos = 0
    for im_name,rects in pos_rects:
        num_pos += len(rects)
        if len(rects) > 0: pos_file.write("%s %d "%(im_name,len(rects)))
        for rect in rects:
            pos_file.write("%d %d %d %d "%(rect.x,rect.y,rect.w,rect.h))
            num_pos += 1
        pos_file.write("\n")
    pos_file.close()
    
    # Add negatives to the negitives file.
    neg_filename = os.path.join(training_dir,neg_name)
    neg_file = open(neg_filename,'w')
    for im_name in neg_images:
        neg_file.write("%s\n"%im_name)
    neg_file.close()
    
    # Create positives vec.
    proc = subprocess.Popen(
          ('/usr/local/bin/opencv-createsamples',
           '-info',pos_name,
           '-vec',pos_vec_name,
           '-num',str(num_pos),
           '-w',str(tile_size[0]),
           '-h',str(tile_size[1]),
           ),
           cwd=training_dir
           ,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT
           )
    
    proc.wait()
    if verbose:
        print proc.stdout.read()
        
    # Run haar training
    success = False
    
    start_time = time.time()
    
    if verbose:
        proc = subprocess.Popen(
              ('/usr/local/bin/opencv-haartraining',
               '-data',cascade_name,
               '-vec',pos_vec_name,
               '-bg',neg_name,
               '-nstages',str(nstages),
               '-mode','ALL',
               '-npos',str(num_pos),
               '-nneg',str(nneg),
               '-mem',str(mem),
               '-w',str(tile_size[0]),
               '-h',str(tile_size[1]),
               '-maxtreesplits',str(maxtreesplits),
               '-minhitrate',str(minhitrate),
               '-maxfalsealarm',str(maxfalsealarm),
               '-mode',mode,
               ),
               cwd=training_dir
               #,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT
               )
    else:
        proc = subprocess.Popen(
              ('/usr/local/bin/opencv-haartraining',
               '-data',cascade_name,
               '-vec',pos_vec_name,
               '-bg',neg_name,
               '-nstages',str(nstages),
               '-mode','ALL',
               '-npos',str(num_pos),
               '-nneg',str(nneg),
               '-mem',str(mem),
               '-w',str(tile_size[0]),
               '-h',str(tile_size[1]),
               '-maxtreesplits',str(maxtreesplits),
               '-minhitrate',str(minhitrate),
               '-maxfalsealarm',str(maxfalsealarm),
               '-mode',mode,
               ),
               cwd=training_dir
               ,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT
               )
    
    while True:
        if proc.poll() != None:
            break
        if time.time() - start_time > max_run_time:
            print "Haar Training time exceeded. Killing process..." 
            os.kill(proc.pid,6) #6 = abort, 3=quit, 9=kill
            proc.wait()
            break
        #out = proc.stdout.read()
        #if verbose:
        #    print out
        time.sleep(1)

    if proc.returncode == 0:
        if verbose: print "Cascade successful."
        success = True
        

    else:
        print "Problem with return code:",proc.returncode
        levels = os.listdir(os.path.join(training_dir,cascade_name))
        nlevels = len(levels)

    
    # Load the detector if training was successful.
    detector = None
    if success:
        detector = CascadeDetector(os.path.join(training_dir,cascade_name+'.xml')) 
    else:
        levels = os.listdir(os.path.join(training_dir,cascade_name))
        nlevels = len(levels)
        if nlevels > 0:
            print "Loading partail cascade..."
            cascade = cvLoadHaarClassifierCascade( os.path.join(training_dir,cascade_name), cvSize(tile_size[0],tile_size[1]))
            cvSave(os.path.join(training_dir,cascade_name+'.xml'),cascade)
            detector = CascadeDetector(os.path.join(training_dir,cascade_name+'.xml'),orig_size=tile_size) 
        else:
            print "Cascade Failure. Could not create classifier."            

    # Clean up the temporary files   
    os.system("rm -rf %s"%training_dir)
    
    time.sleep(5)
    return detector
    
 

SCRAPS_FACE_DATA = os.path.join(pyvision.__path__[0],"data","csuScrapShots")
NONFACE_DATA = os.path.join(pyvision.__path__[0],"data","NonFace")
BAD_CASCADE=os.path.join(pyvision.__path__[0],"config","not_there.xml")


class _TestFaceRecognition(unittest.TestCase):
    ''' Unit tests for the Cascade Detector '''
    
    def setUp(self):
        self.images = []
        self.names = []
        
        
        
        self.eyes = EyesFile(os.path.join(SCRAPS_FACE_DATA,"coords.txt"))
        for filename in self.eyes.files():
            img = Image(os.path.join(SCRAPS_FACE_DATA, filename + ".pgm"))
            self.images.append(img)
            self.names.append(filename)
        
        self.assert_( len(self.images) == 173 )

    
    def test_detect_bad_file(self):
        '''
        If the cascade file does not exist, opencv can crash without warning.
        This makes sure a test is run to make sure the cascade is there.
        '''
        
        self.assertRaises(CascadeNotFound,CascadeDetector,BAD_CASCADE)
        
    def test_face_detection_pickle(self):
        fd = CascadeDetector(OPENCV_CASCADE)
        
        fdt = FaceDetectionTest(name='scraps')

        buffer = pickle.dumps(fd)
        fd = pickle.loads(buffer)
        
        for img in self.images:
            rects = fd(img)
            truth = self.eyes.getFaces(img.filename)
            fdt.addSample(truth,rects,im=img)

        self.assertAlmostEqual( fdt.pos_rate , 0.953, places = 2 )

        
    def test_detect_scraps_opencv(self):
        
        fd = CascadeDetector(OPENCV_CASCADE)
        fdt = FaceDetectionTest(name='scraps')
        
        for img in self.images:
            rects = fd(img)
            truth = self.eyes.getFaces(img.filename)
            fdt.addSample(truth,rects,im=img)

        self.assertAlmostEqual( fdt.pos_rate , 0.953, places = 2 )
        
    def test_detect_scraps_celeb1(self):
        fd = CascadeDetector(CELEB1_CASCADE)
        fdt = FaceDetectionTest(name='scraps')

        for img in self.images:
            rects = fd(img)
            truth = self.eyes.getFaces(img.filename)
            fdt.addSample(truth,rects,im=img)

        self.assertAlmostEqual( fdt.pos_rate , 0.74566473988439308, places = 2 )
        
    def test_detect_scraps_celeb2(self):
        
        fd = CascadeDetector(CELEB2_CASCADE)
        fdt = FaceDetectionTest(name='scraps')
        
        for img in self.images:
            rects = fd(img)
            truth = self.eyes.getFaces(img.filename)
            fdt.addSample(truth,rects,im=img)

        self.assertAlmostEqual( fdt.pos_rate , 0.925, places = 2 )
  

    def test_detector_train(self):

        n = len(self.images)    
        positives = []    
        for img in self.images[:n/2]:
            faces = self.eyes.getFaces(img.filename)
            positives.append([os.path.join(SCRAPS_FACE_DATA,img.filename),faces])   
            
        neg_files = []
        for im_name in os.listdir(NONFACE_DATA):    
            if im_name[-4:] != ".jpg": continue
            neg_files.append(os.path.join(NONFACE_DATA,im_name))

        fd = trainHaarClassifier(positives,neg_files,nstages=6,maxtreesplits=0,max_run_time=300)
        fdt = FaceDetectionTest(name='scraps')
        
        for img in self.images:
            rects = fd(img)
            truth = self.eyes.getFaces(img.filename)
            fdt.addSample(truth,rects,im=img)

        self.assertAlmostEqual( fdt.pos_rate , 0.9942196531791907 )
 


