# Copyright (c) 2008-2025 Optris GmbH & Co. KG

"""
PIF Python3 example. 

2025-08-22

The configuration of the PIF is grouped in the configure_pif() method. 
It checks which PIF-Device is connected and dependent on the available inputs and outputs sets these mode to the first channel of 
each type:

|         Channel         | [deviceIndex, pinIndex] |          Mode          |
|-------------------------|-------------------------|------------------------|
| Analog input (Ai)       |           [0, 0]        | Uncommitted Value      |
| Analog output (Ao)      |           [0, 0]        | Internal Temperature   |
| Digital input (Di)      |           [0, 0]        | Flag Control           |
| Digital output (Do)     |           [0, 0]        | External Communication |
| Dedicated FailSave (Fs) |           [0, 0]        | On                     |

 The direct access of the PIF input values happens in the onThermalFrame() callback via the FrameMetadata object. 
 This example prints the value of each available channel to the standard output.

 Some important notes:
  - This example will use only one camera
  - If a Di is available, the flag must be controlled by the input signal
  - It is also possible (and in many cases more flexible) to configure the PIF via the configuration file. 
 This example will use the mode it configured for the first pin of each channel instead of the mode that is stated in the config file.
  - This is only a small subset of the possible modes for the PIF channels.
  - Please have a look at the documentation to learn more about configuring the modes used in this example as well as the other available modes. 
"""

import sys
import threading
import time
import optris.otcsdk as otc


class SimpleImagerClientPif(otc.IRImagerClient):
    """
    Minimal implementation of an IRImagerClient with additional PIF functionality.

    Bare minimum required to run an imager instance and receive data from it via the Observer pattern.
    Adds a method that configures the Process Interface (PIF) and an additional callback for "Uncommitted Value".
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
        self._imager = otc.IRImagerFactory.getInstance().create("native")
        # Register to receive updated via callbacks
        self._imager.addClient(self)
        # Establish a connection to camera with the provided serial number
        self._imager.connect(serial_number)
        # Thread to run the frame grabbing and image processing
        self._thread = None

        # Time by which the output should be delayed.
        self._DELAY_TIME = 5.
        # Wait-time between outputs.
        self._OUTPUT_INTERVAL = 1.
        # Timestamp gets set when configure_pif() has finished.
        self._configuration_finished = time.time()
        # Timestamp to keep track of the time of the last standard output.
        self._last_output = time.time()
        # Turns off elapsed-time check in onThermalFrame()-callback.
        self._delay_output = True


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


    def configure_pif(self):
        """
        Configures the process interface.
        """
        # Get the PIF interface (returned reference is only valid during an active camera connection)
        pif = self._imager.getPif()

        # Tip: You can change the PIF device type and count at runtime like this:
        # pifConfig = pif.getConfig() # Preserves the existing PIF channel configurations. Create new object to reset them.

        # pifConfig.deviceType  = otc.PifDeviceType_Stackable
        # pifConfig.deviceCount = 1

        # pif.setConfig(pifConfig)


        # Get the type of the connected PIF
        # Returns the type of the PIF that is really connected to the camera
        # Autonomous Cameras (Xi80, Xi 410, Xi 1M): Returns the type that is stored in the config on the camera
        print("\n{} PIF\n".format(otc.pifDeviceTypeToString(self._imager.getPif().getDeviceType())))

        print("{} configurable device(s), {} are actually connected.\n".format(pif.getConfigurableDeviceCount(), pif.getActualDeviceCount()))

        # Check, if connected PIF has a dedicated fail save channel
        hasFailSave = "No"
        if pif.hasFs():
            hasFailSave = "Yes"

        print("{:<15}{:<6}{:<6}{:<6}{:<6}{:<6}".format("AVAILABILITY", "AI", "AO", "DI", "DO", "FS"))

        # Check the number of actual available inputs and outputs
        print("{:<15}{:<6}{:<6}{:<6}{:<6}{:<6}".format("Actual", 
                                                       pif.getActualAiCount(), 
                                                       pif.getActualAoCount(), 
                                                       pif.getActualDiCount(),
                                                       pif.getActualDoCount(),
                                                       hasFailSave))

        # Check the number of configurable inputs and outputs
        print("{:<15}{:<6}{:<6}{:<6}{:<6}{:<6}\n\n".format("Configurable", 
                                                           pif.getConfigurableAiCount(), 
                                                           pif.getConfigurableAoCount(), 
                                                           pif.getConfigurableDiCount(),
                                                           pif.getConfigurableDoCount(),
                                                           hasFailSave))

        # This example configures the first channel (AO, AI, ...) of the first PIF device 
        print("Configuring Channels\n")

        device_index = 0
        pin_index = 0

        # Configure an AI channel
        print("AI{}.{}: ".format(device_index + 1, pin_index + 1), end='')
        if pif.getConfigurableAiCount() >= 1:
            print("Set to \"Uncommitted Value\"")
            
            # Sets the AI to "Uncommitted Value" mode.
            # The converted input values (depending on gain/offset) will be available via the onPifUncommittedValue() callback function
            pif.setAiConfig(otc.PifAiConfig.createUncommittedValue(device_index, pin_index, "Pressure Sensor", "Pa", 0.1, 0.0))
        else:
            print("Not available.")

        # Configure an AO channel
        print("AO{}.{}: ".format(device_index, pin_index), end='')
        if pif.getConfigurableAoCount() >= 1:
            print("Set to \"Internal Temperature\"")

            # Get the default analog output mode (0..10 V or 0..20 mA/4..20 mA) dependent on the connected device
            output_mode = pif.getDefaultAoOutputMode()

            # Sets the AO to "Internal Temperature" mode
            pif.setAoConfig(otc.PifAoConfig.createInternalTemperature(device_index, pin_index, output_mode, 0.1, 0.0))
        else:
            print("Not available.")

        # Configure a DI channel
        print("DI{}.{}: ".format(device_index + 1, pin_index + 1), end='')
        if pif.getConfigurableDiCount() >= 1:
            print("Set to \"Flag Control\"")

            # Sets the DI to "Flag Control" mode
            # The flag therefore cycles when the input switches between high and low
            pif.setDiConfig(otc.PifDiConfig.createFlagControl(device_index, pin_index, True))
        else:
            print("Not available.")

        # Configure a DO channel
        print("DO{}.{}: ".format(device_index + 1, pin_index + 1), end='')
        if pif.getConfigurableDoCount() >= 1:
            print("Set to \"External Communication\"")

            # Sets the DO to "External Communication" which enables the user to control the value of the output
            pif.setDoConfig(otc.PifDoConfig.createExternalCommunication(device_index, pin_index))

            # Set the output to a value
            pif.setDoValue(device_index, pin_index, True)
        else:
            print("Not available.")

        # Configure the Fs channel
        print("FS   : ", end='')
        if pif.hasFs():
            print("Set to \"On\"")

            # Activates the fail safe channel
            pif.setFsConfig(otc.PifFsConfig.createOn())
        else:
            print("Not available.")

        print("\n\nPIF output is delayed for {} seconds...\n".format(self._DELAY_TIME))

        self._configuration_finished = time.time()
          

    def onThermalFrame(self, thermal, meta):
        """
        Called when a new thermal frame is available.
        """
        # Determine the indices of available PIF inputs
        pif_device_count = meta.getPifActualDeviceCount()
        pif_ai_count = meta.getPifAiCountPerDevice()
        pif_di_count = meta.getPifDiCountPerDevice()

        # For readability: Delays output of PIF-input values by DELAY_TIME seconds
        now = time.time()

        if self._delay_output:
            if now - self._configuration_finished < self._DELAY_TIME:
                return
            
            self._delay_output = False
            self._last_output = now

        # For readability: Throttles output of PIF-input values to every OUTPUT_INTERVAL seconds
        if now - self._last_output < self._OUTPUT_INTERVAL:
            return

        self._last_output = now        

        # Access the PIF input values directly
        try:
            for device_index in range(pif_device_count):
                print("PIF Device {}".format(device_index + 1))

                # Analog inputs (voltage as float)
                for pin_index in range(pif_ai_count):
                    print("- AI{}.{} Value: {:.2f} V".format(device_index + 1, pin_index + 1, meta.getPifAiValue(device_index, pin_index)))

                # Digital inputs (boolean)
                for pin_index in range(pif_di_count):
                    print ("- DI{}.{} Value: {}".format(device_index + 1, pin_index + 1, meta.getPifDiValue(device_index, pin_index)))
                
        except otc.SDKException as ex:
            print("Failed to get PIF input value: {}".format(ex))

        print()


    def onFlagStateChange(self, flagState):
       """
       Called when the state of the shutter flag changed.
       """
       print("Flag state: {}\n".format(otc.flagStateToString(flagState)))


    def onPifUncommittedValue(self, name, unit, value):
        """
        Called when the read input voltage on the configured channel has changed.
        """
        print("{}: {} {}\n".format(name, value, unit))



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
      client = SimpleImagerClientPif(serial_number)

      # Configure the process interface
      client.configure_pif()

    except otc.SDKException as ex:
      print(ex)
      return

    # Run
    client.run()


if __name__ == "__main__":
    main()