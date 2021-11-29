#--------------------------------------------------------------------------------------
# Spectrometer imports and helper routines
#--------------------------------------------------------------------------------------

import io
import csv
import time
import ipywidgets as widgets
import matplotlib.pyplot as plt
import numpy as np

from picamera import PiCamera
from PIL import Image, ImageDraw
from time import sleep, strftime
from IPython.display import display, clear_output, HTML, IFrame

from streaming.server import StreamingServer
from streaming import svg

#--------------------------------------------------------------------------------------
# Spectrometer class
#--------------------------------------------------------------------------------------
class Spectrometer():
    debug = None
    dirty = False
    
    #----------------------------------------------------------------------------------
    # Making the GUI
    #----------------------------------------------------------------------------------
    inpWidth = '280px'
    width    = '680px'
    height   = '525px'
    
    # Calibration wavelength
    waveL1 = 544.0
    waveL2 = 611.0
    
    # Links
    localurl  = 'http://localhost:8000/'
    streamurl = 'http://localhost:4664/'

    # Images
    raw = None
    processed = None
    spectrum = None
    wavelength = None
    
    # Other
    scaleFactor = 1
    splash = Image.open('docs/images/specBackground.png')
    mask   = Image.open('docs/images/mask.png')

    butclose = widgets.Button(button_style='danger', description='Shutdown', disabled=False,
                              layout=widgets.Layout(width='auto', margin='10px 0px 0px 0px'))

    out      = widgets.Output(layout=widgets.Layout(width=width, height=height))
    status   = widgets.HTML(value="Ready ..", layout=widgets.Layout(width='auto', margin='0px 0px 0px 15px'))

    # Measurement TAB -----------------------------------------------------------------
    m_head1  = widgets.HTML(value="<h4>Experiment</h4>")
    m_name   = widgets.Text(value='', description='Scientist:', disabled=False, layout=widgets.Layout(width='auto'))
    m_light  = widgets.Text(value='', placeholder='Light source details', description='Light:', disabled=False, 
                            layout=widgets.Layout(width='auto'))
    m_sample = widgets.Text(value='None', placeholder='Transmission sample details', description='Sample:', disabled=False, 
                            layout=widgets.Layout(width='auto'))
    m_notes  = widgets.Textarea(value='', placeholder='Experiment notes', description='Notes:', rows=5, disabled=False,
                                layout=widgets.Layout(width='auto'))

    m_head2 = widgets.HTML(value="<h4>Settings</h4>")
    m_expo  = widgets.BoundedFloatText(description='Exposure', value=0.2, min=0.1, max=5.0, step=0.1, 
                                        layout=widgets.Layout(width='auto'))
    m_rot   = widgets.BoundedFloatText(value=270.0, min=0.0, max=360.0, step=0.5,
                                       description="Rotation:", disabled=False, layout=widgets.Layout(width='auto'))

    m_neopix = widgets.ColorPicker(concise=False, description='NeoPixel', value='#000000', disabled=True, 
                                   layout=widgets.Layout(width='auto'))

    m_butstart = widgets.Button(button_style='primary', description='Update Feed', disabled=False,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    m_butraw = widgets.Button(button_style='success', description='Take Measurement', disabled=False,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    
    m_left   = widgets.VBox([m_head1, m_name, m_light, m_sample, m_notes, 
                             m_head2, m_neopix, m_expo, m_rot, m_butstart, m_butraw, butclose],
                         layout=widgets.Layout(height=height, border='solid 1px #ddd'))
    m_tab    = widgets.HBox([m_left, out])
    
    # Processing TAB -------------------------------------------------------------------
    p_head = widgets.HTML(value="<h4>Processing</h4>")
    p_time   = widgets.Text(value='', placeholder='Timestamp', description='Timestamp:', disabled=True, 
                            layout=widgets.Layout(width='auto'))
    
    p_head1 = widgets.HTML(value="<h4>Crop area</h4>")
    p_crop  = [None, None, None, None]
    p_crop[0] = widgets.Text(value='', description="Top left x:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[1] = widgets.Text(value='', description="Top left y:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[2] = widgets.Text(value='', description="Btm right x:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[3] = widgets.Text(value='', description="Btm right y:", disabled=False, layout=widgets.Layout(width='auto'))
    p_head2 = widgets.HTML(value="<h4>Calibration</h4>")
    p_pix1  = widgets.Text(value='', description="Line 1", disabled=False, layout=widgets.Layout(width='auto'))
    p_pix2  = widgets.Text(value='', description="Line 2", disabled=False, layout=widgets.Layout(width='auto'))

    p_butpro = widgets.Button(button_style='primary', description='Process', disabled=True,
                            layout=widgets.Layout(width='100%', margin='25px 0px 0px 0px'))
        
    p_left   = widgets.VBox([p_head, p_time, p_head1, p_crop[0], p_crop[1], p_crop[2], p_crop[3],
                           p_head2, p_pix1, p_pix2, p_butpro], layout=widgets.Layout(height=height, border='solid 1px #ddd'))
    p_tab    = widgets.HBox([p_left, out])


    # Making GUI widget ---------------------------------------------------------------
    right = widgets.VBox([out, status], layout=widgets.Layout(margin='3px 0px 2px 5px', border='solid 1px #888'))
    tabs = widgets.Tab(layout=widgets.Layout(width=inpWidth))
    tabs.set_title(0, 'Measure')
    tabs.set_title(1, 'Process')
    tabs.children = (m_left, p_left)
    
    gui = widgets.HBox([tabs, right])
    #----------------------------------------------------------------------------------
    # Callbacks
    #----------------------------------------------------------------------------------
    def updateFeed(self,c):
        if self.dirty:
            self.updateStream()
            self.dirty = False

        self.scamera.updateFeed(None)

    #----------------------------------------------------------------------------------
    def updateOverlay(self,c):
        self.scamera.updateOverlayProcess(self.p_crop, self.p_pix1.value, self.p_pix2.value)

    #----------------------------------------------------------------------------------
    def updateLight(self,c):
        self.m_light.value = "NeoPixel - "+self.m_neopix.value
        self.pixels.fill(hex_to_rgb(self.m_neopix.value))  

    #----------------------------------------------------------------------------------
    def runMeasure(self,b):       
        self.tabs.selected_index = 1
        self.status.value = "Please wait .."
        
        self.scamera.stopStream()
        self.p_time.value = strftime("%Y%m%d-%H%M%S") 
        self.setLCD(self.splash) 
        
        self.scamera.updateOverlayProcess(self.p_crop, self.p_pix1.value, self.p_pix2.value)
        self.p_butpro.disabled = False
        self.status.value = "Adjust parameters as needed. When you are happy to proceeed click Process .."
        
    #--------------------------------------------------------------------------------------
    def runProcess(self,b):
        self.p_butpro.disabled = True
        self.status.value = "Processing started .."

        self.raw = self.takePicture()
        self.dirty = True

        self.status.value = "Cropping .."
        cropvals = [int(v.value) for v in self.p_crop]
        self.processed = self.raw.crop(cropvals)

        self.status.value = "Updating LCD .."
        self.setLCD(self.processed)

        self.status.value = "Scaling .."
        self.processed = self.adjustBrightness(self.processed)

        self.status.value = "Converting to spectrum .."
        self.wavelength, self.spectrum = self.getSpectrum(self.processed, self.waveL1, self.waveL2, 
                                                          int(self.p_pix1.value), int(self.p_pix2.value))

        with self.out:
            fig, ax = plt.subplots()
            ax.set_xlabel('Wavelength (nm)')
            ax.set_xlim(auto=True)
            ax.set_ylim(auto=True)
            ax.plot(self.wavelength, self.spectrum, color='blue')

            clear_output(wait=True)
            display(ax.figure)
            plt.savefig("docs/images/spectrum-"+self.p_time.value+".jpg")
            plt.close()

        self.status.value = "Saving results .."
        self.raw.save("docs/images/raw-"+self.p_time.value+".jpg")
        self.processed.save("docs/images/processed-"+self.p_time.value+".jpg")
        self.saveCSV("docs/data/spectrum-"+self.p_time.value+".csv", self.spectrum, self.wavelength)

        self.status.value = "Creating web pages .."
        self.createHTML()
        self.updateLight("#000000")
        
        self.status.value = "Done .."

    #--------------------------------------------------------------------------------------
    def saveCSV(self,fname, spectrum, wavelength):
        with open(fname, 'w', encoding='UTF8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Wavelength","Intensity"])

            for l,i in zip(wavelength, spectrum):
                writer.writerow([l,i])

    #--------------------------------------------------------------------------------------
    def createHTML(self):

        shutter = 1000000 * float(self.m_expo.value)

        hfile="docs/experiment-"+self.p_time.value+".html"

        with open("docs/template.html", "rt") as fin:
            with open(hfile, "wt") as fout:
                for line in fin:
                    line = line.replace('%%lightSource%%', str(self.m_light.value))
                    line = line.replace('%%measurementTaken%%', str(self.p_time.value))
                    line = line.replace('%%scientistName%%', str(self.m_name.value))
                    line = line.replace('%%transmissionSample%%', str(self.m_sample.value))
                    line = line.replace('%%shutter%%', str(shutter))
                    line = line.replace('%%experimentNotes%%', str(self.m_notes.value))

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
                       entry.format(self.p_time.value, self.m_name.value, 
                                    self.m_light.value, self.m_sample.value))

        with open("docs/index.html", "wt") as fout:
            fout.write(out)
            
    #----------------------------------------------------------------------------------
    # Spectrometer methods
    #----------------------------------------------------------------------------------
    def getSpectrum(self, processed, wavelength1, wavelength2, pixel1, pixel2):
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
    def adjustBrightness(self,image):
        pixels = np.asarray(image)
        maxcol = [pixels[:,:,0].max(),pixels[:,:,1].max(),pixels[:,:,2].max()]
        self.scaleFactor = int(255 / max(maxcol))
        adjusted = self.scaleFactor*pixels
        
        return Image.fromarray(np.uint8(adjusted))

    #--------------------------------------------------------------------------------------
    def takePicture(self):  
        stream = io.BytesIO()
        self.scamera.camera.capture(stream, format='jpeg')
        stream.seek(0)
        raw = Image.open(stream)

        return raw

    #----------------------------------------------------------------------------------
    # Methods
    #----------------------------------------------------------------------------------
    def initNeoPixel(self):
        import time
        import board
        import busio
        from rainbowio import colorwheel
        from adafruit_seesaw import seesaw, neopixel

        NEOPIXEL_PIN = 9  # Pin NeoPixel is connected to (9, 10, 11, 14, 15, 24, or 25 )
        NEOPIXEL_NUM = 1  # no more than 60!

        i2c_bus = busio.I2C(board.SCL, board.SDA)
        ss = seesaw.Seesaw(i2c_bus)
        self.pixels = neopixel.NeoPixel(ss, NEOPIXEL_PIN, NEOPIXEL_NUM)

        self.pixels.brightness = 1.0 # Full brightness
        self.pixels.fill((0,0,0))    # Light off
        
    #----------------------------------------------------------------------------------
    def initLCD(self):
        import ST7735

        self.disp = ST7735.ST7735(port=0,cs=1,dc=9,backlight=12,rotation=270,spi_speed_hz=10000000)
        self.disp.begin()
        self.setLCD(self.splash)

    #----------------------------------------------------------------------------------
    def setLCD(self, img):
        if (self.lcd):
            lcd=img.resize((self.disp.width, self.disp.height))
            lcd.paste(self.mask, (0,0), self.mask)
            self.disp.display(lcd)

    #----------------------------------------------------------------------------------
    def setCrop(self,crop):
        for i, c in enumerate(crop):
            self.p_crop[i].value = str(c)
            
    #----------------------------------------------------------------------------------
    def updateStream(self):
        with self.out:
            clear_output(wait=True)
            display(IFrame(self.streamurl, width=680, height=550)) 
            self.dirty = False

    #----------------------------------------------------------------------------------
    def show(self):
        display(self.gui)
        self.updateStream()
        
    #----------------------------------------------------------------------------------
    def __init__(self, lcd, neopixel):
        self.lcd = lcd
        self.neopixel = neopixel
        self.scamera = StreamingCamera(self.m_expo, self.m_rot)
        
        if (neopixel):
            self.m_neopix.disabled = False
            self.initNeoPixel()
            self.m_neopix.observe(self.updateLight)
            
        if (lcd):
            self.initLCD()

        self.m_butstart.on_click(self.updateFeed)
        self.m_butraw.on_click(self.runMeasure)
        self.p_butpro.on_click(self.runProcess)
        self.butclose.on_click(self.shutdown)
        
        for i in range(4):
            self.p_crop[i].on_submit(self.updateOverlay)
        self.p_pix1.on_submit(self.updateOverlay)
        self.p_pix2.on_submit(self.updateOverlay)
                
    #----------------------------------------------------------------------------------
    def shutdown(self, b):
        self.close()

    #----------------------------------------------------------------------------------
    def close(self):
        self.scamera.server.close()
        self.scamera.camera.close()  
        print('Spectrometer object deleted')
        clear_output()
        del self
        
#--------------------------------------------------------------------------------------
# StreamingCamera class
#--------------------------------------------------------------------------------------
class StreamingCamera():

    exposure  = 0.2
    framerate = 5.
    rotation  = 270.0
    raw = None

    #----------------------------------------------------------------------------------
    def stopStream(self):
        try:
            self.server._stop_recording()
        except:
            pass

    #----------------------------------------------------------------------------------
    def startStream(self):
        try:
            self.server._start_recording()
        except:
            pass

    #----------------------------------------------------------------------------------
    def updateFeed(self, c):
        self.exposure  = float(self.expo.value)
        self.framerate = 1. / float(self.expo.value)
        self.srotation  = float(self.rot.value)

        self.expo.disabled=True
        self.stopStream()
        self.server._camera.framerate = self.framerate
        self.server._camera.shutter_speed = int(1000000 * self.exposure)
        self.server._camera.rotation = self.rotation
        self.startStream()
        self.expo.disabled=False
        self.updateOverlay(self.exposure, self.framerate, self.rotation)

    #----------------------------------------------------------------------------------
    def updateOverlay(self, exp, fps, rot):
        text="LEGO Spectrometer - Exposure {:.1f} sec - Framerate {:.2f} fps - Angle {:.1f}".format(exp, fps, rot)        
        doc = svg.Svg(width=self.camera.resolution.width, height=self.camera.resolution.height)
        doc.add(svg.Text(text, x=10, y=25, fill='yellow', font_size=16))
        self.server.send_overlay(str(doc))
        
    #----------------------------------------------------------------------------------
    def updateOverlayProcess(self, crop, pix1, pix2):
        c = [int(v.value) for v in crop]

        doc = svg.Svg(width=self.camera.resolution.width, height=self.camera.resolution.height)
        doc.add(svg.Rect(x=c[0], y=c[1], width=c[2]-c[0], height=c[3]-c[1], fill="none",
                         style='stroke:yellow;stroke-width:2px'))
        doc.add(svg.Line(x1=pix1, y1=0, x2=pix1, y2=self.camera.resolution.height, style='stroke:green;stroke-width:3px'))
        doc.add(svg.Line(x1=pix2, y1=0, x2=pix2, y2=self.camera.resolution.height, style='stroke:red;stroke-width:3px'))
        self.server.send_overlay(str(doc))

    #----------------------------------------------------------------------------------
    def close(self):
        self.server.close()
        self.camera.close()  
        print('StreamingCamera object close')
    
    #----------------------------------------------------------------------------------
    def __init__(self, expo, rot):
        streaming_bitrate = 1000000
        mdns_name = ''        
        
        self.expo = expo
        self.rot  = rot
        
        self.camera = PiCamera()
        self.camera.resolution = (648, 486)        
        self.camera.framerate= 1. / self.exposure
        self.camera.rotation = 270
        self.camera.iso = 800
        self.camera.shutter_speed = int(1000000 * self.exposure)
        self.camera.awb_mode = 'off'
        self.camera.awb_gains = (1, 1)

        self.camera.start_preview()
        self.server = StreamingServer(self.camera, bitrate=streaming_bitrate,  mdns_name=mdns_name)

#--------------------------------------------------------------------------------------
# Helpers
#--------------------------------------------------------------------------------------
def hex_to_rgb(value):
    
    value = value.lstrip('#')
    lv = len(value)

    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))