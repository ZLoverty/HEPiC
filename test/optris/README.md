# Python 3 Examples

Examples illustrating how to use the Python 3 language bindings of the SDK.


## Dependencies
The examples require Python 3 to be installed on your machine. On Linux you can use the package manager `apt` to install it:

```bash
sudo apt install python3
```

On Windows you need to navigate to the Python [website](https://www.python.org/) and download the installer for Windows. After
the installation some additional Python libraries need to be installed. On Linux you can use `apt` again. On Windows you might
prefer to utilize the built-in package manager `pip` of Python.

__Linux__
```bash
sudo apt install python3-numpy 
```

__Windows__
```powershell
pip.exe install numpy
```

## Examples

### enumeration
Displays enumeration events (detection of attached cameras) on the command line.

Run the example with the following command:

__Linux__
```bash
python3 enumeration.py
```

__Windows__
```powershell
python.exe .\enumeration.py
```

### minimal
Views the current flag state and the dimensions of thermal frame on the command line. This is the minimal implementation required to retrieve thermal data from 
an Optris thermal camera.

Run the example with the following command:

__Linux__
```bash
python3 minimal.py <serial number>
```

__Windows__
```powershell
python.exe .\minimal.py <serial number>
```

If no serial number is provided, the program will use the first compatible camera on the USB port.

### pif
Displays details about a connected process interface, tries to configure the first channel of each available type and outputs the read input values of
all PIF input channels.

Run the example with the following command:

__Linux__
```bash
python3 pif.py <serial number>
```

__Windows__
```powershell
cd Release
python.exe .\pif.py <serial number>
```

If no serial number is provided, the program will use the first compatible camera attached via USB.

### simple_view
Views a false color image based on the thermal data from the camera.

This example requires the OpenCV bindings for Python. You can install these dependencies, for example, with `pip` or `apt`:

__Linux__
```bash
sudo apt install python3-opencv
```

__Windows__
```powershell
pip.exe install opencv-python
```

Run the example with the following command:

__Linux__
```bash
python3 simple_view.py <serial number>
```

__Windows__
```powershell
python.exe .\simple_view.py <serial number>
```

If no serial number is provided, the program will use the first compatible camera it finds on the USB port.