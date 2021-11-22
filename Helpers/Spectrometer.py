#--------------------------------------------------------------------------------------
# Spectrometer imports and helper routines
#--------------------------------------------------------------------------------------

import io
import csv
import ipywidgets as widgets
import matplotlib.pyplot as plt
import numpy as np

from picamera import PiCamera
from PIL import Image, ImageDraw
from time import sleep, strftime
from IPython.display import clear_output, HTML

plt.rcParams['figure.figsize'] = [10, 8]

# Some flags
useLCD      = False
useNeoPixel = False

#--------------------------------------------------------------------------------------
def initLCD():
    import ST7735
    useLCD = True
    
    disp = ST7735.ST7735(port=0,cs=1,dc=9,backlight=12,rotation=270,spi_speed_hz=10000000)
    disp.begin()
    
return

#--------------------------------------------------------------------------------------
def initNeoPixel():
    import time
    import board
    import busio
    from rainbowio import colorwheel
    from adafruit_seesaw import seesaw, neopixel
    useNeoPixel = True
    
    NEOPIXEL_PIN = 9  # change to Pin NeoPixel is connected to (9, 10, 11, 14, 15, 24, or 25 )
    NEOPIXEL_NUM = 1  # no more than 60!

    i2c_bus = busio.I2C(board.SCL, board.SDA)
    ss = seesaw.Seesaw(i2c_bus)
    pixels = neopixel.NeoPixel(ss, NEOPIXEL_PIN, NEOPIXEL_NUM)

    pixels.brightness = 1.0 # Full brightness
    pixels.fill((0,0,0))    # Light off
    
    return

#--------------------------------------------------------------------------------------
def takePicture(shutter):
    
    camera = PiCamera()
    stream = io.BytesIO()
    
    # Needed because maximum exposure is 1/framerate!
    if (shutter > 200000):
        framerate = 1000000./shutter
    else:
        framerate = 5.
        
    try:
        # Full camera resolution is 2592 x 1944 - we run at 1/4 resolution 
        camera.resolution = (648, 486)        
        camera.framerate= framerate
        camera.rotation = 270
        camera.iso = 800
        camera.shutter_speed = shutter
        camera.awb_mode = 'off'
        camera.awb_gains = (1, 1)

        sleep(1)

        camera.capture(stream, format='jpeg')
        stream.seek(0)
        raw = Image.open(stream)
    finally:
        camera.close()
    return raw

#--------------------------------------------------------------------------------------
def adjustBrightness(image):
    
    pixels = np.asarray(image)
    maxcol = [pixels[:,:,0].max(),pixels[:,:,1].max(),pixels[:,:,2].max()]
    factor = int(255 / max(maxcol))
    
    adjusted = factor*pixels
    return Image.fromarray(np.uint8(adjusted)), factor # Convert it back to an image

#--------------------------------------------------------------------------------------
def getSpectrum(processed, wavelength1, wavelength2, pixel1, pixel2):
    
    spectrum = np.asarray(processed)            # Convery to Numpy array for calculations
    spectrum = np.average(spectrum, axis=(0,2)) # Average columns and color values
    spectrum = spectrum-(0.9*min(spectrum))     # Subtract baseline
    
    if (wavelength1 > wavelength2):             # Swap if wavelengths are in wrong order
        temp = wavelength1
        wavelength1 = wavelength2
        wavelength2 = temp
        
    wavelength = np.arange(float(len(spectrum)))
    factor = (wavelength2 - wavelength1) / (pixel2 - pixel1)
    wavelength = wavelength1 + (wavelength - pixel1) * factor
    
    return wavelength, spectrum

#--------------------------------------------------------------------------------------
def saveCSV(fname, spectrum, wavelength):
    with open(fname, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Wavelength","Intensity"])

        for l,i in zip(wavelength, spectrum):
            writer.writerow([l,i])

#--------------------------------------------------------------------------------------
def createHTML(lightSource, scientistName, transmissionSample, experimentNotes, measurementTaken, shutter):
    
    hfile="docs/experiment-"+measurementTaken+".html"
    
    with open("docs/template.html", "rt") as fin:
        with open(hfile, "wt") as fout:
            for line in fin:
                line = line.replace('%%lightSource%%', str(lightSource))
                line = line.replace('%%measurementTaken%%', str(measurementTaken))
                line = line.replace('%%scientistName%%', str(scientistName))
                line = line.replace('%%transmissionSample%%', str(transmissionSample))
                line = line.replace('%%shutter%%', str(shutter))
                line = line.replace('%%experimentNotes%%', str(experimentNotes))

                fout.write(line)

    entry='''<!--%%entry%%-->
        <tr><td><img src="images/processed-{0}.jpg" align="right">
            Scientist: <strong>{1}</strong><br>
            Light source: <strong>{2}</strong><br>
            Transmission sample: <strong>{3}</strong><br>
            Date and time: <strong>{0}</strong><br>
            <a href="experiment-{0}.html" target="_blank"><button>Details</button></a></td></tr>
        '''
    
    out=""
    with open("docs/index.html", "rt") as fin:
        for line in fin:
            out += line.replace('<!--%%entry%%-->', 
                   entry.format(measurementTaken, scientistName, lightSource, transmissionSample))
            
    with open("docs/index.html", "wt") as fout:
        fout.write(out)
        
#--------------------------------------------------------------------------------------
