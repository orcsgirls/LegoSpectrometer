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
    
    #----------------------------------------------------------------------------------
    # Making the GUI
    #----------------------------------------------------------------------------------
    inpWidth = '275px'
    width    = '770px'
    height   = '600px'
    
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
    
    # Measurement TAB -----------------------------------------------------------------
    m_head1  = widgets.HTML(value="<h4>Experiment</h4>")
    m_name   = widgets.Text(value='', description='Scientist:', disabled=False, layout=widgets.Layout(width='auto'))
    m_light  = widgets.Text(value='', placeholder='Light source details', description='Light:', disabled=False, 
                            layout=widgets.Layout(width='auto'))
    m_sample = widgets.Text(value='None', placeholder='Transmission sample details', description='Sample:', disabled=False, 
                            layout=widgets.Layout(width='auto'))
    m_notes  = widgets.Textarea(value='', placeholder='Experiment notes', description='Notes:', rows=6, disabled=False,
                                layout=widgets.Layout(width='auto'))
    m_time   = widgets.Text(value='', placeholder='Timestamp', description='Timestamp:', disabled=True, 
                            layout=widgets.Layout(width='auto'))

    m_head2 = widgets.HTML(value="<h4>Settings</h4>")
    m_expo   = widgets.BoundedFloatText(description='Exposure', value=0.2, min=0.1, max=5.0, step=0.1, 
                                        layout=widgets.Layout(width='auto'))

    m_neopix = widgets.ColorPicker(concise=False, description='NeoPixel', value='#000000', disabled=True, 
                                   layout=widgets.Layout(width='auto'))
    m_butraw = widgets.Button(button_style='success', description='Measure', disabled=False,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    m_butclose = widgets.Button(button_style='danger', description='Shutdown', disabled=False,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    
    m_out    = widgets.Output(layout=widgets.Layout(width=width, height=height, border='solid 1px #ddd'))
    m_status = widgets.HTML(value="Ready ..")
    
    m_left   = widgets.VBox([m_head1, m_time, m_name, m_light, m_sample, m_notes, 
                             m_head2, m_neopix, m_expo, m_butraw, m_butclose, m_status],
                         layout=widgets.Layout(height=height, border='solid 1px #ddd',
                                               margin='0px 5px 0px 0px', width=inpWidth))
    m_tab    = widgets.HBox([m_left, m_out])
    
    # Processing TAB -------------------------------------------------------------------
    p_head1 = widgets.HTML(value="<h4>Image</h4>")
    p_rot   = widgets.Text(value='', description="Angle:", disabled=False, layout=widgets.Layout(width='auto'))
    
    p_head2 = widgets.HTML(value="<h4>Crop area</h4>")
    p_crop  = [None, None, None, None]
    p_crop[0] = widgets.Text(value='', description="Top left x:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[1] = widgets.Text(value='', description="Top left y:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[2] = widgets.Text(value='', description="Btm right x:", disabled=False, layout=widgets.Layout(width='auto'))
    p_crop[3] = widgets.Text(value='', description="Btm right y:", disabled=False, layout=widgets.Layout(width='auto'))

    p_head3 = widgets.HTML(value="<h4>Calibration</h4>")
    p_pix1  = widgets.Text(value='', description="Line 1", disabled=False, layout=widgets.Layout(width='auto'))
    p_pix2  = widgets.Text(value='', description="Line 2", disabled=False, layout=widgets.Layout(width='auto'))

    p_butupd = widgets.Button(button_style='success', description='Update plot', disabled=True,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    p_butpro = widgets.Button(button_style='primary', description='Process', disabled=True,
                            layout=widgets.Layout(width='100%', margin='5px 0px 0px 0px'))
    
    p_out    = widgets.Output(layout=widgets.Layout(width=width, height=height, border='solid 1px #ddd', margin='0px 5px 0px 0px'))
    p_status = widgets.HTML(value="Ready ..")
    
    p_left   = widgets.VBox([p_head1, p_rot, p_head2, p_crop[0], p_crop[1], p_crop[2], p_crop[3],
                           p_head3, p_pix1, p_pix2, p_butupd, p_butpro, p_status],
                           layout=widgets.Layout(height=height, width=inpWidth,
                                                 border='solid 1px #ddd', margin='0px 5px 0px 0px'))
    p_tab    = widgets.HBox([p_left, p_out])

    # Publishing tab ------------------------------------------------------------------
    l_log = widgets.Output()
    l_msg = widgets.HTML(value="<center>Make sure you run <tt>python3 -m http.server</tt> in the <tt>docs</tt> directory.", 
                       layout=widgets.Layout(width='95%'))
    l_tab = widgets.VBox([l_log, l_msg], layout=widgets.Layout(height=height))
    
    # Making GUI widget ---------------------------------------------------------------
    gui = widgets.Tab()
    gui.set_title(0, 'Measure')
    gui.set_title(1, 'Process')
    gui.set_title(2, 'Log book')
    gui.children = (m_tab, p_tab, l_tab)
    
    #----------------------------------------------------------------------------------
    # Callbacks
    #----------------------------------------------------------------------------------
    def updateLight(self,c):
        self.m_light.value = "NeoPixel - "+self.m_neopix.value
        self.pixels.fill(hex_to_rgb(self.m_neopix.value))  

    #----------------------------------------------------------------------------------
    def runMeasure(self,b):       
        self.m_butraw.disabled = True
        self.setLCD(self.splash)
        
        self.m_time.value = strftime("%Y%m%d-%H%M%S") 
        shutter = int(1000000 * float(self.m_expo.value))

        self.m_status.value = 'Capturing image ..'
        self.raw = self.takePicture()
        self.m_status.value = "Done .."
        self.m_butraw.disabled = False

        self.runProcessUpdate(None)
        self.p_butupd.disabled = False
        self.p_butpro.disabled = False
        
        self.gui.selected_index = 1

    #--------------------------------------------------------------------------------------
    def runProcessUpdate(self,b):
        self.p_butupd.disabled = True
        self.p_butpro.disabled = True
        self.p_status.value = "Updating .."

        angle = float(self.p_rot.value)
        if(angle != 0.0):
            self.raw = self.raw.rotate(angle)

        dummy = self.raw.copy()
        draw = ImageDraw.Draw(dummy)
        cropvals = [int(v.value) for v in self.p_crop]
        draw.rectangle(cropvals, outline=(255, 255, 0), width=2)
        draw.line((int(self.p_pix1.value), 0, int(self.p_pix1.value), self.raw.height), fill=(  0,255,  0), width=5)
        draw.line((int(self.p_pix2.value), 0, int(self.p_pix2.value), self.raw.height), fill=(255,  0,  0), width=5)

        with self.p_out:
            fig, ax = plt.subplots()
            ax.grid(color='yellow', linestyle='dotted', linewidth=1)
            ax.set_xticks(np.arange(0, dummy.width, 50.0))
            ax.set_yticks(np.arange(0, dummy.width, 50.0))
            ax.imshow(dummy)

            clear_output(wait=True)
            display(ax.figure)
            plt.close()
            
        self.p_status.value = "Cropping .."
        cropvals = [int(v.value) for v in self.p_crop]
        self.processed = self.raw.crop(cropvals)

        self.p_status.value = "Updating LCD .."
        self.setLCD(self.processed)

        self.p_status.value = "Updated .."
        self.p_butupd.disabled = False
        self.p_butpro.disabled = False

    #--------------------------------------------------------------------------------------
    def runProcess(self,b):
        self.p_butupd.disabled = True
        self.p_butpro.disabled = True

        self.p_status.value = "Scaling .."
        self.processed = self.adjustBrightness(self.processed)

        self.p_status.value = "Converting to spectrum .."
        self.wavelength, self.spectrum = self.getSpectrum(self.processed, self.waveL1, self.waveL2, 
                                                          int(self.p_pix1.value), int(self.p_pix2.value))

        with self.p_out:
            fig, ax = plt.subplots()
            ax.set_xlabel('Wavelength (nm)')
            ax.set_xlim(auto=True)
            ax.set_ylim(auto=True)
            ax.plot(self.wavelength, self.spectrum, color='blue')

            clear_output(wait=True)
            display(ax.figure)
            plt.savefig("docs/images/spectrum-"+self.m_time.value+".jpg")
            plt.close()

        self.p_status.value = "Saving results .."
        self.raw.save("docs/images/raw-"+self.m_time.value+".jpg")
        self.processed.save("docs/images/processed-"+self.m_time.value+".jpg")
        self.saveCSV("docs/data/spectrum-"+self.m_time.value+".csv", self.spectrum, self.wavelength)

        self.p_status.value = "Creating web pages .."
        self.createHTML()
        self.updateWeblog()
        self.updateLight("#000000")
        
        self.p_status.value = "Done .."
        self.p_butupd.disabled = False
        self.p_butpro.disabled = False
        
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

        hfile="docs/experiment-"+self.m_time.value+".html"

        with open("docs/template.html", "rt") as fin:
            with open(hfile, "wt") as fout:
                for line in fin:
                    line = line.replace('%%lightSource%%', str(self.m_light.value))
                    line = line.replace('%%measurementTaken%%', str(self.m_time.value))
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
                       entry.format(self.m_time.value, self.m_name.value, 
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
    def updateWeblog(self):
        with self.l_log:
            clear_output(wait=True)
            display(IFrame(self.localurl, width=900, height=self.height))
            
    #----------------------------------------------------------------------------------
    def updateStream(self):
        with self.m_out:
            clear_output(wait=True)
            display(IFrame(self.streamurl, width=680, height=550))  

    #----------------------------------------------------------------------------------
    def show(self):
        display(self.gui)
        self.updateStream()
        self.updateWeblog()
        
    #----------------------------------------------------------------------------------
    def __init__(self, lcd, neopixel):
        self.lcd = lcd
        self.neopixel = neopixel
        self.scamera = StreamingCamera(self.m_expo)
        
        if (neopixel):
            self.m_neopix.disabled = False
            self.initNeoPixel()
            self.m_neopix.observe(self.updateLight)
            
        if (lcd):
            self.initLCD()

        self.m_butraw.on_click(self.runMeasure)
        self.m_butclose.on_click(self.shutdown)
        self.p_butupd.on_click(self.runProcessUpdate)
        self.p_butpro.on_click(self.runProcess)
        self.m_expo.observe(self.scamera.updateFramerate)
        
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

    exposure = 0.2
    raw = None

    #----------------------------------------------------------------------------------
    def updateFramerate(self, c):
        new_exposure  = float(self.expo.value)
        framerate     = 1. / float(self.expo.value)

        if(new_exposure != self.exposure):
            self.expo.disabled=True
            self.exposure = new_exposure
            self.server._stop_recording()
            self.server._camera.framerate = framerate
            self.server._camera.shutter_speed = int(1000000 * self.exposure)
            self.server._start_recording()
            self.expo.disabled=False
            self.updateOverlay()

    #----------------------------------------------------------------------------------
    def updateOverlay(self):
        text="LEGO Spectrometer - Exposure {:.1f} sec - Framerate {:.2f} fps".format(self.exposure, 1./self.exposure)
        doc = svg.Svg(width=self.camera.resolution.width, height=self.camera.resolution.height)
        doc.add(svg.Text(text, x=10, y=25, fill='yellow', font_size=18))
        self.server.send_overlay(str(doc))
        
    #----------------------------------------------------------------------------------
    def close(self):
        self.server.close()
        self.camera.close()  
        print('StreamingCamera object close')
    
    #----------------------------------------------------------------------------------
    def __init__(self, expo):
        streaming_bitrate = 1000000
        mdns_name = ''        
        
        self.expo = expo
        
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