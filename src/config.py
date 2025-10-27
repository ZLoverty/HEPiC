from dataclasses import dataclass

@dataclass
class Config:
    name = "HEPiC"
    version = "0.0.0"
    test_mode = False
    test_image_folder = "~/Documents/GitHub/HEPiC/test/filament_images_captured"
    default_host = "192.168.114.48"
    data_frequency = 10 # Hz, defines how many data points are recorded per time
    status_frequency = 5 # Hz, defines how often the status panel refreshes
    tmp_data_maxlen = 1000 # length of temporarily cached data
    final_data_maxlen = 10000000
