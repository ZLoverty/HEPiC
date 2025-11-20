import sys
import os
import numpy as np
import cv2
from ctypes import *
from pathlib import Path

# 确保 MvImport 路径正确
try:
    if os.name == 'nt': # Windows
        sdk_path = str(Path(os.getenv('MVCAM_COMMON_RUNENV')) / "Samples" / "Python" / "MvImport")
        os.add_dll_directory(r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64")
    else: # Linux/Mac
        sdk_path = "/opt/MVS/Samples/Python/MvImport"
    sys.path.append(sdk_path)
    CAM_LIB_LOADED = True
except Exception as e:
    print(f"ERROR: Camera lib failed to load! Camera will not work.")
    CAM_LIB_LOADED = False

if CAM_LIB_LOADED:
    try:
        from MvCameraControl_class import *
    except Exception as e:
        print(f"无法导入 MvCameraControl_class。请确保 SDK 已安装，并且路径正确。")
        print(f"SDK 路径: {sdk_path}")
        print(f"错误: {e}")
        print(f"ERROR: Camera failed to initiate!")


class HikVideoCapture:
    """
    主动设置参数的、高效的 Hikvision 相机封装类
    
    用法:
        MvCamera.MV_CC_Initialize()
        try:
            # 主动设定为 BGR8 格式
            cap = HikCameraPro(camera_index=0, pixel_format=PixelType_Gvsp_BGR8_Packed)
            
            # 或者让它自动使用相机的默认格式
            # cap = HikCameraPro(camera_index=0)
            
            while True:
                ret, frame = cap.read()
                if ret:
                    cv2.imshow("frame", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            cap.release()
        finally:
            MvCamera.MV_CC_Finalize()
    """

    def __init__(self, camera_index=0, width: int | None = None, height: int | None = None, exposure_time: float | None = None, center_roi: bool = True, pixel_format=None):

        self.cam = None
        self.buffer = None
        self.payload_size = 0
        self.is_open = False
        
        # --- 图像转换参数 (将在 _set_camera_props 中被赋值) ---
        self.img_width = 0
        self.img_height = 0
        self.img_bpp = 1  # 默认为1 (Mono8)
        self.conversion_code = None  # OpenCV 转换码
        
        # 1. 枚举设备
        device_list = self._enum_devices()
        if device_list.nDeviceNum == 0:
            raise Exception("未找到设备!")
        if camera_index >= device_list.nDeviceNum:
            raise Exception(f"无效的相机索引 {camera_index}")

        # 2. 创建句柄
        self.cam = MvCamera()
        st_device_info = cast(device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)).contents
        ret = self.cam.MV_CC_CreateHandle(st_device_info)
        if ret != MV_OK:
            raise Exception(f"创建句柄失败! ret[0x{ret:x}]")

        # 3. 打开设备
        ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != MV_OK:
            print("请检查电脑和相机是否在同段IP。")
            raise Exception(f"打开设备失败! ret[0x{ret:x}]")
        self.is_open = True # 标记为已打开，以便 _set_camera_props 可以工作

        # 4. (仅 GigE) 探测最佳包大小
        if st_device_info.nTLayerType == MV_GIGE_DEVICE:
            self._optimize_gige_packet_size()

        # 5. 设置触发模式为 Off (连续采集)
        ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        if ret != MV_OK:
            raise Exception(f"设置触发模式为 Off 失败! ret[0x{ret:x}]")

        # ==========================================================
        # 6. 【核心】主动设置或获取相机参数
        # ==========================================================
         # 1. 设置像素格式 (如果提供了)
        ret = self.cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8) # use mono8 format always
        if ret != MV_OK:
            raise Exception(f"设置像素格式失败! ret[0x{ret:x}]。 确保相机支持该格式。")
            
        self._set_camera_props(width, height)

        if center_roi:
            try:
                width_max = self._get_int_value("WidthMax")
                height_max = self._get_int_value("HeightMax")
                
                # 使用整数除法计算偏移量
                offset_x = (width_max - width) // 2
                offset_y = (height_max - height) // 2
                
                print(f"传感器最大分辨率: {width_max}x{height_max}。正在计算居中偏移...")
                
                if self.cam.MV_CC_SetIntValue("OffsetX", offset_x): print(f"成功设置 OffsetX 为: {offset_x}")
                else: print(f"警告: 设置 OffsetX {offset_x} 失败。")
                
                if self.cam.MV_CC_SetIntValue("OffsetY", offset_y): print(f"成功设置 OffsetY 为: {offset_y}")
                else: print(f"警告: 设置 OffsetY {offset_y} 失败。")

            except Exception as e:
                print(f"警告: 自动居中ROI时出错: {e}。ROI可能未居中。")

        # 7. 获取 Payload 大小并准备缓冲区
        self.payload_size = self._get_int_value("PayloadSize")
        if self.payload_size == 0:
            raise Exception("获取 PayloadSize 失败!")
            
        # 缓冲区大小必须为 PayloadSize
        self.buffer = (c_ubyte * self.payload_size)()
        self.frame_info = MV_FRAME_OUT_INFO_EX()

        # 1. 关闭自动曝光
        # 参数名: "ExposureAuto"
        # 值: "Off"
        ret = self.cam.MV_CC_SetEnumValueByString("ExposureAuto", "Off")
        if ret != 0:
            print(f"关闭自动曝光失败! ret = {ret:#x}") # 使用十六进制打印错误码
        else:
            print("自动曝光已关闭 (ExposureAuto -> Off)")

        # 2. 手动设置曝光时间
        # 参数名: "ExposureTime"
        # 值: 10000.0 (单位：微秒 μs)
        # 
        # 示例：设置 10000 μs = 10 ms = 0.01 s
        # 理论上允许的最大帧率 ≈ 1 / 0.01s = 100 FPS
        if exposure_time is not None:
            exposure_time_us = 1000.0 * exposure_time # normally exposure time is measured in ms, convert it to us for the cam  
            ret = self.cam.MV_CC_SetFloatValue("ExposureTime", exposure_time_us)
            if ret != 0:
                print(f"设置曝光时间失败! ret = {ret:#x}")
            else:
                print(f"曝光时间已设置为: {exposure_time_us} μs")

        # 8. 开始取流
        ret = self.cam.MV_CC_StartGrabbing()
        if ret != MV_OK:
            raise Exception(f"开始取流失败! ret[0x{ret:x}]")
        
        print(f"相机 {camera_index} 已打开。")
        print(f"  -> 分辨率: {self.img_width}x{self.img_height}")

    def _enum_devices(self):
        device_list = MV_CC_DEVICE_INFO_LIST()
        tlayer_type = MV_GIGE_DEVICE | MV_USB_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(tlayer_type, device_list)
        if ret != MV_OK:
            raise Exception(f"枚举设备失败! ret[0x{ret:x}]")
        return device_list

    def _optimize_gige_packet_size(self):
        n_packet_size = self.cam.MV_CC_GetOptimalPacketSize()
        if int(n_packet_size) > 0:
            ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", n_packet_size)
            if ret != MV_OK:
                print(f"警告: 设置最佳包大小失败! ret[0x{ret:x}]")
        else:
            print(f"警告: 获取最佳包大小失败! ret[0x{n_packet_size:x}]")
            
    def _get_int_value(self, key):
        st_param = MVCC_INTVALUE()
        memset(byref(st_param), 0, sizeof(MVCC_INTVALUE))
        ret = self.cam.MV_CC_GetIntValue(key, st_param)
        if ret != MV_OK:
            raise Exception(f"获取参数 '{key}' 失败! ret[0x{ret:x}]")
        return st_param.nCurValue

    def _get_enum_value(self, key):
        st_param = MVCC_ENUMVALUE()
        memset(byref(st_param), 0, sizeof(MVCC_ENUMVALUE))
        ret = self.cam.MV_CC_GetEnumValue(key, st_param)
        if ret != MV_OK:
            raise Exception(f"获取参数 '{key}' 失败! ret[0x{ret:x}]")
        return st_param.nCurValue

    def _set_camera_props(self, width, height):
        """主动设置或获取参数，并设置内部转换变量"""
        
       
        
        # 2. 设置宽度 (如果提供了)
        if width is not None:
            ret = self.cam.MV_CC_SetIntValue("Width", width)
            if ret != MV_OK:
                raise Exception(f"设置宽度失败! ret[0x{ret:x}]。")
        
        # 3. 设置高度 (如果提供了)
        if height is not None:
            ret = self.cam.MV_CC_SetIntValue("Height", height)
            if ret != MV_OK:
                raise Exception(f"设置高度失败! ret[0x{ret:x}]。")

        # 4. 【关键】获取最终的实际参数
        self.img_width = self._get_int_value("Width")
        self.img_height = self._get_int_value("Height")
        self.pixel_format_int = self._get_enum_value("PixelFormat")
        
        # 5. 根据最终的像素格式，预先设置好转换参数
        if self.pixel_format_int == PixelType_Gvsp_Mono8:
            self.img_bpp = 1
            self.conversion_code = None # Mono8 无需转换
        elif self.pixel_format_int == PixelType_Gvsp_BGR8_Packed:
            self.img_bpp = 3
            self.conversion_code = None # BGR8 无需转换
        elif self.pixel_format_int == PixelType_Gvsp_BayerRG8:
            self.img_bpp = 1
            self.conversion_code = cv2.COLOR_BAYER_RG2BGR
        elif self.pixel_format_int == PixelType_Gvsp_BayerBG8:
            self.img_bpp = 1
            self.conversion_code = cv2.COLOR_BAYER_BG2BGR
        elif self.pixel_format_int == PixelType_Gvsp_BayerGB8:
            self.img_bpp = 1
            self.conversion_code = cv2.COLOR_BAYER_GB2BGR
        elif self.pixel_format_int == PixelType_Gvsp_BayerGR8:
            self.img_bpp = 1
            self.conversion_code = cv2.COLOR_BAYER_GR2BGR
        else:
            raise Exception(f"不支持的像素格式! [0x{self.pixel_format_int:x}]")

    def read(self):
        """
        高效读取一帧图像。
        不再检查像素格式，而是直接使用 __init__ 中设置好的转换参数。
        """
        if not self.is_open:
            return False, None

        # 尝试获取一帧图像，超时 1000ms
        ret = self.cam.MV_CC_GetOneFrameTimeout(self.buffer, self.payload_size, self.frame_info, 1000)
        
        if ret == MV_OK:
            # --- 高效图像转换 ---
            
            # 1. 计算有效数据长度 (防止缓冲区末尾有无效数据)
            data_len = self.img_width * self.img_height * self.img_bpp
            
            # 2. 将 ctypes 缓冲区转换为 NumPy 数组 (零拷贝)
            #    注意: .frombuffer() 会创建一个视图，但它可能是只读的。
            #    如果需要修改(例如原地转换)，可能需要 .copy()
            image_data = self.buffer[:data_len]
            
            image = np.array(image_data).astype("uint8").reshape(self.img_height, self.img_width)
                
            return True, image
        
        else:
            # print(f"读取帧失败! ret[0x{ret:x}]")
            return False, None

    def release(self):
        if not self.is_open:
            return
        self.is_open = False
        print("正在释放相机...")
        self.cam.MV_CC_StopGrabbing()
        self.cam.MV_CC_CloseDevice()
        self.cam.MV_CC_DestroyHandle()
        self.cam = None
        self.buffer = None

    def __del__(self):
        self.release()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# --- 示例用法 ---
def main():
    
    ret = MvCamera.MV_CC_Initialize()
    if ret != MV_OK:
        print(f"SDK 初始化失败!")
        return

    try:
        # === 示例 1: 主动设置为 BGR8 ===
        # (确保你的相机支持 BGR8，否则会抛出异常)
        print("--- 正在尝试以 BGR8 模式打开 ---")
        cap = HikVideoCapture(
            camera_index=0,
            width=512,
            height=512,
            exposure_time=30000 
            
        )
        
        # === 示例 2: 主动设置为 Mono8, 640x480 ===
        # print("--- 正在尝试以 Mono8 640x480 模式打开 ---")
        # cap = HikCameraPro(
        #     camera_index=0, 
        #     width=640,
        #     height=480,
        #     pixel_format=PixelType_Gvsp_Mono8
        # )

        # === 示例 3: 使用相机当前默认设置 ===
        # print("--- 正在尝试以默认模式打开 ---")
        # cap = HikCameraPro(camera_index=0)


        with cap:
            print("相机已打开, 按 'q' 退出。")
            
            while True:
                ret, frame = cap.read()
                
                if ret:
                    cv2.imshow("Hikvision Camera Pro", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as e:
        print(f"发生错误: {e}")
    
    finally:
        print("正在反初始化 SDK...")
        MvCamera.MV_CC_Finalize()
        cv2.destroyAllWindows()
        print("程序退出。")


if __name__ == "__main__":
    main()