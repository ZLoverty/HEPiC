# HEPiC

HEPiC is the Hotend Extrusion Platform (based on raspberry Pi) Control software. It is designed for simultaneous measurements of relevant quantities in FDM processes. 

## Installation

1. Download and install Hikrobot SDK https://www.hikrobotics.com/en/machinevision/service/download/

2. Download and install Optris SDK https://github.com/Optris/otcsdk_downloads

3. Install FFmpeg  `winget install ffmpeg`

4. Clone HEPiC git repo

5. Create venv in HEPiC folder 

    ```
    python -m venv .venv
    ```

5. Activate venv

6. In folder "HEPiC", run `pip install .` 

6. Now, input `hepic` to launch the software. 
