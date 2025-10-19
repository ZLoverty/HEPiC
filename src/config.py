from dataclasses import dataclass

@dataclass
class Config:
    name = "HEPiC"
    version = "0.0.0"
    test_mode = True
    test_image_folder = "~/Documents/GitHub/etp_ctl/test/filament_images_simulated"
    default_host = "192.168.0.107"
    data_frequency = 10 # Hz, defines how many data points per time
    tmp_data_len = 100 # length of temporarily cached data
    final_data_maxlen = 10000000
