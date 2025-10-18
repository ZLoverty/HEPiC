# Copyright (c) 2008-2025 Optris GmbH & Co. KG

"""
Simple View Python3 example. 

2025-02-19 
"""

import sys
import threading
import cv2
import numpy as np
import optris.otcsdk as otc


class ImagerShow(otc.IRImagerClient):
    """
    A more feature rich implementation of an IRImagerClient that converts thermal frames to false color images and
    displays them.

    An IRImager acts as an observer to an IRImager implementation that retrieves and processes thermal data from
    Optris thermal cameras.
    """

    def __init__(self, serial_number):
        """
        Constructor.
        """
        # Required to initialize base class
        super().__init__()

        # The factory is implemented as a Singleton. Therefore, you have to call getInstance()
        # first before you can create an IRImager object.
        #
        # The native implementation allows you to access the thermal data of cameras connected
        # via USB or Ethernet.
        self._imager = otc.IRImagerFactory.getInstance().create('native')
        # Register to receive updates via callbacks
        self._imager.addClient(self)
        # Establish a connection to the camera with the provided serial number
        self._imager.connect(serial_number)

        # Create an imager builder that converts thermal frames to false color images
        # The color format BGR is required because of OpenCV uses this pixel color oder by default
        self._builder = otc.ImageBuilder(colorFormat=otc.ColorFormat_BGR, widthAlignment=otc.WidthAlignment_OneByte)

        # The image grabbing and processing is done in a separate thread while the rendering of the
        # resulting image will be done in the main thread
        self._thread             = None
        self._thermal_frame_lock = threading.Lock()

        self._keep_rendering = threading.Event()

        self._flag_state      = otc.FlagState_Initializing
        self._flag_state_lock = threading.Lock()

        self._thermal_frame         = otc.ThermalFrame()
        self._thermal_frame_updated = False

        self._fps = otc.FramerateCounter(100)


    def run(self):
        """
        Main run method.
        """
        # Create and start the image grabbing/processing thread
        self._thread = threading.Thread(target=self._imager.run)
        self._thread.start()

        self._keep_rendering.set()

        fps = 0.
        flag_state = otc.FlagState_Initializing
        
        # Thermal frame to false color image conversion and rendering loop
        while self._keep_rendering.is_set():
            # Get the latest thermal frame if there is one
            do_render = False # 增加一个标志，决定是否渲染
            with self._thermal_frame_lock:
                if self._thermal_frame_updated and not self._thermal_frame.isEmpty():
                    self._builder.setThermalFrame(thermalFrame=self._thermal_frame)
                    self._thermal_frame_updated = False
                    fps = self._fps.getFps()
                    do_render = True

              

            with self._flag_state_lock:
               flag_state = self._flag_state
               if do_render:
                  # Generate the false color image
                  self._builder.convertTemperatureToPaletteImage()

                  # Copy the image data to an empty NumPy array...
                  image = np.empty((self._builder.getHeight(), self._builder.getWidth(), 3), dtype=np.uint8)
                  self._builder.copyImageDataTo(image)

                  # Writes a legend upon the false color image
                  image = self.drawOverlay(image, fps, flag_state)

                  # ...and display it
                  cv2.imshow('Optris Imager - {} (S/N {})'.format(otc.deviceTypeToString(self._imager.getDeviceType()), self._imager.getSerialNumber()), image)

            # Check for keyboard inputs indicating that the user wants to quit by pressing the q key
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
               break
            elif key == ord('r'):
               self._imager.forceFlagEvent()

        # Clean up
        cv2.destroyAllWindows()

        self._imager.stopRunning()
        self._thread.join()
          

    # Client callbacks
    def onThermalFrame(self, thermal, meta):
        """
        Called when a new thermal frame is available.
        """
        # Since two threads are used synchronization is required
        with self._thermal_frame_lock:
            # Store the thermal frame for processing and rendering by the main thread
            self._thermal_frame         = thermal
            self._thermal_frame_updated = True

            self._fps.trigger()


    def onFlagStateChange(self, flagState):
        """
        Called when the state of the internal shutter flag changes.
        """
        with self._flag_state_lock:
          self._flag_state = flagState


    def onConnectionLost(self):
        """
        Called when the connection to the camera is lost and can not be recovered.
        """
        self._keep_rendering.clear()


    def onConnectionTimeout(self):
        """
        Called when the SDK has not received frames from the camera for a while.
        """
        self._keep_rendering.clear()


    def drawOverlay(self, image, fps, flag_state):
        """
        Superimposes an overlay over the false color image.
        """
        # Overlay text
        text = ['Src: {} fps'.format(round(fps, 1)), 'Flag State: {}'.format(otc.flagStateToString(flag_state)), 'q: Quit', 'r: Refresh Flag']

        # Text font face
        font = cv2.FONT_HERSHEY_SIMPLEX
        size = 0.4
        thickness = 1
        line_margin = 10

        # Overlay position
        x = image.shape[1] - 150
        y = 25

        # Draw overlay
        for i, line in enumerate(text):
          line_height = cv2.getTextSize(line, font, size, thickness)[0][1]

          cv2.putText(image, line, (x, y + i * (line_height + line_margin)), font, size, (0, 255, 0), thickness, lineType = cv2.LINE_AA)

        return image


def main():
    """
    Main entry point.
    """
    # Get the serial number from command line argument
    # With a serial number of 0 the first compatible camera will be chosen
    serial_number = 0
    if len(sys.argv) >= 2:
       serial_number = int(sys.argv[1])
    
    # Initialize the SDK by providing logger verbosity
    otc.Sdk.init(otc.Verbosity_Info, otc.Verbosity_Off, sys.argv[0])

    client = None
    try:
      client = ImagerShow(serial_number)

    except otc.SDKException as ex:
      print(ex)
      return

    # Run
    client.run()


if __name__ == "__main__":
    main()