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
from IPython.display import clear_output, HTML, IFrame

global angle, butpro, butraw, butupd, calib1, calib2, crop, cropbox, expo
global light, name, neopix, notes, out, pix1, pix2, pixelL1, pixelL2, pout
global processed, pstatus, raw, sample, scientist, specfig, spectrum, status
global time, tor, waveL1, waveL2, wavelength, pixels, disp

#--------------------------------------------------------------------------------------
# Some setup routines
#--------------------------------------------------------------------------------------
def initLCD():
    import ST7735
    
    global disp
    
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
    
    global pixels
    
    NEOPIXEL_PIN = 9  # Pin NeoPixel is connected to (9, 10, 11, 14, 15, 24, or 25 )
    NEOPIXEL_NUM = 1  # no more than 60!

    i2c_bus = busio.I2C(board.SCL, board.SDA)
    ss = seesaw.Seesaw(i2c_bus)
    pixels = neopixel.NeoPixel(ss, NEOPIXEL_PIN, NEOPIXEL_NUM)

    pixels.brightness = 1.0 # Full brightness
    pixels.fill((0,0,0))    # Light off
    
    return

#--------------------------------------------------------------------------------------
# Spectrometer user interface call back functions (when button is pressed)
#--------------------------------------------------------------------------------------
def updateLight(c):
    
    global light, neopix, pixels
    
    light.value = "NeoPixel - "+neopix.value
    pixels.fill(hex_to_rgb(neopix.value))  
    
    return

#--------------------------------------------------------------------------------------
def runMeasure(b):
    
    global butraw, time, raw, neopix, butupd, butpro, out, status, pixels
    
    butraw.disabled = True
    time.value = strftime("%Y%m%d-%H%M%S") 
    shutter = int(1000000 * float(expo.value))
    
    status.value = 'Aquiring data for {:.1f} seconds ..'.format(float(expo.value))
    raw = takePicture(shutter)
    status.value = "Processing .."

    with out:
        ax = plt.gca()
        ax.grid(color='yellow', linestyle='dotted', linewidth=1)
        ax.set_xticks(np.arange(0, raw.width, 100.0))
        ax.imshow(raw)

        clear_output(wait=True)
        display(ax.figure)
    
    neopix.value = "#000000"
    pixels.fill((0,0,0))
    status.value = "Done .."
    butraw.disabled = False
    
    runProcessUpdate(None)
    butupd.disabled = False
    butpro.disabled = False

    return

#--------------------------------------------------------------------------------------
def runProcessUpdate(b):
    
    global pstatus, rot, pix1, pix2, cropvals, pout, butupd, butpro, raw, crop

    butupd.disabled = True
    butpro.disabled = True
    pstatus.value = "Updating .."
    
    angle = float(rot.value)
    if(angle != 0.0):
        raw = raw.rotate(angle)
        
    temp = raw.copy();
    draw = ImageDraw.Draw(temp)
    cropvals = [int(v.value) for v in crop]
    draw.rectangle(cropvals, outline=(255, 255, 0), width=2)
    draw.line((int(pix1.value), 0, int(pix1.value), raw.height), fill=(  0,255,  0), width=5)
    draw.line((int(pix2.value), 0, int(pix2.value), raw.height), fill=(255,  0,  0), width=5)

    with pout:
        ax = plt.gca()
        ax.grid(color='yellow', linestyle='dotted', linewidth=1)
        ax.set_xticks(np.arange(0, raw.width, 50.0))
        ax.imshow(temp)

        clear_output(wait=True)
        display(ax.figure)

    pstatus.value = "Updated .."
    butupd.disabled = False
    butpro.disabled = False

    return

#--------------------------------------------------------------------------------------
def runProcess(b):
    
    global butupd, butpro, pstatus, processed, raw, pout, time, spectrum, wavelength, disp
    global name, light, sample, notes, time, waveL1, waveL1

    butupd.disabled = True
    butpro.disabled = True
    pstatus.value = "Cropping .."
    
    cropvals = [int(v.value) for v in crop]
    processed = raw.crop(cropvals)
    
    pstatus.value = "Scaling .."
    processed = adjustBrightness(processed)
    
    pstatus.value = "Converting to spectrum .."
    wavelength, spectrum = getSpectrum(processed, waveL1, waveL1, int(pix1.value), int(pix2.value))
    
    with pout:
        plt.clf()
        ax = plt.gca()
        ax.set_xlabel('Wavelength (nm)')
        ax.plot(wavelength, spectrum, color='blue')
        
        clear_output(wait=True)
        display(ax.figure)

    pstatus.value = "Updating LCD .."
    disp.display(processed.resize((disp.width, disp.height)))
    
    pstatus.value = "Saving results .."
    plt.savefig("docs/images/spectrum-"+time.value+".jpg")
    raw.save("docs/images/raw-"+time.value+".jpg")
    processed.save("docs/images/processed-"+time.value+".jpg")
    saveCSV("docs/data/spectrum-"+time.value+".csv", spectrum, wavelength)

    pstatus.value = "Creating web pages .."
    createHTML()
    
    pstatus.value = "Done .."
    butupd.disabled = False
    butpro.disabled = False

    return

#--------------------------------------------------------------------------------------
def makeMeasureTab():
    
    global name, light, sample, notes, time, expo, neopix, butraw, status, out
    
    head1  = widgets.HTML(value="<h4>Experiment</h4>")
    name   = widgets.Text(value='', description='Scientist:', disabled=False)
    light  = widgets.Text(value='', placeholder='Light source details', description='Light:', disabled=False)
    sample = widgets.Text(value='None', placeholder='Transmission sample details', description='Sample:', disabled=False)
    notes  = widgets.Textarea(value='', placeholder='Experiment notes', description='Notes:', rows=6, disabled=False)
    time   = widgets.Text(value='', placeholder='Timestamp', description='Timestamp:', disabled=True)

    head2 = widgets.HTML(value="<h4>Settings</h4>")
    expo   = widgets.FloatSlider(value=1.0, min=0.0, max=6.0, step=0.1, description='Exposure:',
                                 disabled=False, continuous_update=False, orientation='horizontal', readout=True,
                                 readout_format='.1f')
    neopix = widgets.ColorPicker(concise=False, description='NeoPixel', value='#000000', disabled=False)
    butraw = widgets.Button(button_style='success', description='Measure', 
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    
    out    = widgets.Output(layout=widgets.Layout(width='600px', height='500px', border='solid 1px #ddd'))
    status = widgets.HTML(value="Ready ..")
    
    left   = widgets.VBox([head1, time, name, light, sample, notes, head2, neopix, expo, butraw, status],
                         layout=widgets.Layout(height='500px', border='solid 1px #ddd',
                                               margin='0px 10px 0px 0px'))
    tab    = widgets.HBox([left, out])

    # Register call backs
    butraw.on_click(runMeasure)
    neopix.observe(updateLight)
    
    return tab

#--------------------------------------------------------------------------------------
def makeProcessingTab():
    
    global rot, crop, pix1, pix2, butupd, butpro, pout, pstatus
    
    head1 = widgets.HTML(value="<h4>Image</h4>")
    rot  = widgets.Text(value='', description="Angle:", disabled=False)
    
    head2 = widgets.HTML(value="<h4>Crop area</h4>")
    crop  = [None, None, None, None]
    crop[0] = widgets.Text(value='', description="Top left x:", disabled=False)
    crop[1] = widgets.Text(value='', description="Top left y:", disabled=False)
    crop[2] = widgets.Text(value='', description="Btm right x:", disabled=False)
    crop[3] = widgets.Text(value='', description="Btm right y:", disabled=False)

    head3 = widgets.HTML(value="<h4>Calibration</h4>")
    pix1  = widgets.Text(value='', disabled=False)
    pix2  = widgets.Text(value='', disabled=False)

    butupd = widgets.Button(button_style='success', description='Update plot', disabled=True,
                            layout=widgets.Layout(width='100%', margin='10px 0px 0px 0px'))
    butpro = widgets.Button(button_style='primary', description='Process', disabled=True,
                            layout=widgets.Layout(width='100%', margin='5px 0px 0px 0px'))
    
    pout    = widgets.Output(layout=widgets.Layout(width='600px', height='500px', border='solid 1px #ddd'))
    pstatus = widgets.HTML(value="Ready ..")
    
    left   = widgets.VBox([head1, rot, head2, crop[0], crop[1], crop[2], crop[3],
                           head3, pix1, pix2, butupd, butpro, pstatus],
                           layout=widgets.Layout(height='500px', 
                                                 border='solid 1px #ddd', margin='0px 10px 0px 0px'))
    tab    = widgets.HBox([left, pout])

    # Register call backs    
    butupd.on_click(runProcessUpdate)
    butpro.on_click(runProcess)
    
    return tab

#--------------------------------------------------------------------------------------
def makePublishingTab():
    
    log = widgets.Output(layout=widgets.Layout(height='500px'))
    msg = widgets.HTML(value="<center>Make sure you run <tt>python3 -m http.server</tt> in the <tt>docs</tt> directory.", 
                       layout=widgets.Layout(width='95%'))
    with log:
        display(IFrame('http://orcspi.local:8000/', width=900, height=500))
    
    return widgets.VBox([log, msg])

#--------------------------------------------------------------------------------------
def spectrometerControl(w1, w2, scientist, angle, pixelL1, pixelL2, calib1, calib2, cropbox):
    
    global name, rot, pix1, pix2, crop, waveL1, waveL2
    
    # Create widgets for tabs
    measure = makeMeasureTab()
    processing = makeProcessingTab()
    publish = makePublishingTab()

    # Make Tabs
    gui = widgets.Tab()
    gui.set_title(0, 'Measure')
    gui.set_title(1, 'Process')
    gui.set_title(2, 'Log book')
    gui.children = (measure, processing, publish)
    
    # Some defaults
    name.value = scientist
    rot.value = str(angle)
                         
    pix1.value = str(pixelL1)
    pix2.value = str(pixelL2)    
    pix1.description="Pix "+calib1+":"
    pix2.description="Pix "+calib2+":"
    
    for i in range(4):
        crop[i].value=str(cropbox[i])
        
    waveL1 = w1
    waveL2 = w2
    
    # Display
    display(gui)
    
    return

#--------------------------------------------------------------------------------------
# Spectrometer creating user interface routines
#--------------------------------------------------------------------------------------
def hex_to_rgb(value):
    
    value = value.lstrip('#')
    lv = len(value)

    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

#--------------------------------------------------------------------------------------
# Spectrometer processing routines from SpectrometerContril.ipynb
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
    
    global pstatus
    
    pixels = np.asarray(image)
    maxcol = [pixels[:,:,0].max(),pixels[:,:,1].max(),pixels[:,:,2].max()]
    factor = int(255 / max(maxcol))
    pstatus.value = 'Brightness factor used {:.1f} ..'.format(factor)

    adjusted = factor*pixels
    

    return Image.fromarray(np.uint8(adjusted))

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

    return

#--------------------------------------------------------------------------------------
def createHTML():
    
    global light, name, notes, time,expo
    
    shutter = 1000000 * float(expo.value)
    
    hfile="docs/experiment-"+time.value+".html"
    
    with open("docs/template.html", "rt") as fin:
        with open(hfile, "wt") as fout:
            for line in fin:
                line = line.replace('%%lightSource%%', str(light.value))
                line = line.replace('%%measurementTaken%%', str(time.value))
                line = line.replace('%%scientistName%%', str(name.value))
                line = line.replace('%%transmissionSample%%', str(sample.value))
                line = line.replace('%%shutter%%', str(shutter))
                line = line.replace('%%experimentNotes%%', str(notes.value))

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
                   entry.format(time.value, name.value, light.value, sample.value))
            
    with open("docs/index.html", "wt") as fout:
        fout.write(out)
    
    return

#--------------------------------------------------------------------------------------
