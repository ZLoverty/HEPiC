# Copyright (c) 2008-2025 Optris GmbH & Co. KG

"""
Enumeration Python3 example. 

2025-03-31 
"""

import sys
import time
import optris.otcsdk as otc


class SimpleEnumerationClient(otc.EnumerationClient):
    """
    Simple example implementations of an EnumerationClient that outputs enumeration events to the console.

    An EnumerationClient serves as observer to the EnumerationManger that constantly checks whether new devices 
    are attached or exiting ones are removed.
    """

    def __init__(self):
        """
        Constructor.
        """
        # Required to initialize base class
        super().__init__()
        
        self.print_header()
        
        # Register this instance as a client/observer with the EnumerationManger.
        # The EnumerationManger is implemented using the Singleton pattern. Therefore, you need to call
        # its static getInstance() to interact with it.
        self._manager = otc.EnumerationManager.getInstance()
        self._manager.addClient(self)

        # Thread to run the detection logic of the EnumerationManager
        self._thread = None
    

    def run(self):
        """
        Main run method.
        """
        # The EnumerationManger was already started in a separate thread by the Sdk::init() method. 
        # Therefore, the main thread has nothing to do but wait for keyboard interrupts.
        while(True):
            # Sleep and wait for Ctrl + C to be pressed. Note: EnumerationManager.run() does not recognize
            # a keyboard interrupt!
            try:
                time.sleep(1.)
            except KeyboardInterrupt:
                break


    def onDeviceDetected(self, deviceInfo):
        """ 
        Called when a new device was detected.

        This happens, for example, if a camera is plugged in to the computer via USB.
        """
        self.print_event("Detected", deviceInfo)
    

    def onDeviceDetectionLost(self, deviceInfo):
        """
        Called when a previously detected device is now longer found.

        This happens, for example, if a camera is unplugged from the computer.
        """
        self.print_event("Lost", deviceInfo)


    def print_header(self):
        """
        Prints out the header for the enumeration events.
        """
        print("Enumeration Events (Ctrl + C to quit)\n")
        print("{:<15}{:<15}{:<15}{:<15}{:<15}{:<15}".format("EVENT", 
                                                            "DEVICE TYPE", 
                                                            "S/N", 
                                                            "FIRMWARE REV", 
                                                            "HARDWARE REV", 
                                                            "CONNECTION TYPE"))

    def print_event(self, event, deviceInfo):
        """
        Prints out an enumeration event.
        """
        print("{:<15}{:<15}{:<15}{:<15}{:<15}{:<15}".format(event, 
                                                            otc.deviceTypeToString(deviceInfo.getDeviceType()), 
                                                            deviceInfo.getSerialNumber(), 
                                                            deviceInfo.getFirmwareRevision(),
                                                            deviceInfo.getHardwareRevision(), 
                                                            deviceInfo.getConnectionInterface()))

def main():
    """ 
    Main entry point.
    """
    # Initialize the SDK by providing logger verbosity
    otc.Sdk.init(otc.Verbosity_Error, otc.Verbosity_Off, sys.argv[0])

    client = SimpleEnumerationClient()
    client.run()


if __name__ == "__main__":
    main()