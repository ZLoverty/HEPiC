# Copyright (c) 2008-2025 Optris GmbH & Co. KG

"""
Minimal Python3 example. 

2025-04-01
"""

import sys
import threading
import time
import optris.otcsdk as otc


class SimpleImagerClient(otc.IRImagerClient):
    """
    Minimal implementation of an IRImagerClient.

    Bare minimum required to run an imager instance and receive data from it via the Observer pattern.
    See simple_view for a more comprehensive implementation.
    """

    def __init__(self, serial_number):
        """
        Constructor.
        """
        # Required to initialize base class
        super().__init__()

        # Latest state of the shutter flag
        self._flag_state = otc.FlagState_Initializing

        # Measures frames per second
        self._fps = otc.FramerateCounter(100)

        # The factory is implemented as a Singleton. Therefore, you have to call getInstance()
        # first before you can create an IRImager object.
        #
        # The native implementation allows you to access the thermal data of cameras connected
        # via USB or Ethernet.
        self._imager = otc.IRImagerFactory.getInstance().create("native")
        # Register to receive updated via callbacks
        self._imager.addClient(self)
        # Establish a connection to camera with the provided serial number
        self._imager.connect(serial_number)

        # Thread to run the frame grabbing and image processing
        self._thread = None


    def run(self):
        """
        Main run method.
        """
        # Create and start the image grabbing/processing thread
        self._thread = threading.Thread(target=self._imager.run)
        self._thread.start()

        while(True):
            # Sleep and wait for Ctrl + C to be pressed. Note: IRImager.run() does not recognize
            # a keyboard interrupt!
            try:
                time.sleep(1.)
            except KeyboardInterrupt:
                break
        
        # Stop the processing and join the thread
        self._imager.stopRunning()
        self._thread.join()
          

    def onThermalFrame(self, thermal, meta):
        """
        Called when a new thermal frame is available.
        """
        self._fps.trigger()
        
        # When the flag transitioned out of Initializing the thermal data is valid and can be displayed.
        if self._flag_state != otc.FlagState_Initializing:
            print("{:<10}{:<10}{:<10}{:<20}{:<15}\r".format(thermal.getWidth(), 
                                                            thermal.getHeight(),
                                                            round(self._fps.getFps(), 0),
                                                            round(thermal.getTemperature(int(thermal.getWidth() / 2.), int(thermal.getHeight() / 2.)), 2), 
                                                            otc.flagStateToString(self._flag_state)),
                                                            end = '')


    def onFlagStateChange(self, flagState):
        """
        Called when the state of the shutter flag changed.
        """
        # When the flag transitioned out of Initializing the thermal data is valid. Thus, print the header of the output table.
        if flagState != self._flag_state and self._flag_state == otc.FlagState_Initializing:
            print()
            print("Thermal Frame\n")
            print("{:<10}{:<10}{:<10}{:<20}{:<15}".format("WIDTH", "HEIGHT", "FPS", "TEMP CENTER PIXEL", "FLAG STATE"))

        self._flag_state = flagState


def main():
    """
    Main entry point.
    """
    # Get the serial number from command line argument
    # With a serial number of 0 the first compatible camera will be chosen
    serial_number = 0
    if len(sys.argv) >= 2:
       serial_number = int(sys.argv[1])
       return
    
    # Initialize the SDK by providing logger verbosity
    otc.Sdk.init(otc.Verbosity_Info, otc.Verbosity_Off, sys.argv[0])

    client = None
    try:
      client = SimpleImagerClient(serial_number)

    except otc.SDKException as ex:
      print(ex)
      return

    # Run
    client.run()


if __name__ == "__main__":
    main()