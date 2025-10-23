import sys
import os
import numpy as np
import cv2
from ctypes import *

# 假设 MvImport 目录在你项目的父目录或 Python 路径中
# 你需要根据你的项目结构调整 MvImport 的路径
try:
    # 尝试使用 MVS 示例中的标准路径
    sdk_path = os.getenv('MVCAM_COMMON_RUNENV') + "/Samples/Python/MvImport"
    sys.path.append(sdk_path)
    from MvCameraControl_class import *
except Exception as e:
    print(f"无法导入 MvCameraControl_class，请确保 MVS SDK Python 示例路径已正确添加到 sys.path")
    print(f"错误: {e}")
    sys.exit(-1)


class HikCamera:
    """
    一个用于海康机器人的 OpenCV 风格的相机封装类

    用法:
        # 必须先初始化和反初始化 SDK
        MvCamera.MV_CC_Initialize()
        
        try:
            cap = HikCamera(camera_index=0)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("读取失败")
                    break
                
                cv2.imshow("frame", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            cap.release()
            cv2.destroyAllWindows()

        except Exception as e:
            print(f"相机出错: {e}")
            
        finally:
            MvCamera.MV_CC_Finalize()
    """

    def __init__(self, camera_index=0):
        self.cam = None
        self.buffer = None
        self.payload_size = 0
        self.frame_info = MV_FRAME_OUT_INFO_EX()
        self.is_open = False

        # 1. 枚举设备
        device_list = MV_CC_DEVICE_INFO_LIST()
        tlayer_type = MV_GIGE_DEVICE | MV_USB_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(tlayer_type, device_list)
        if ret != MV_OK:
            raise Exception(f"枚举设备失败! ret[0x{ret:x}]")

        if device_list.nDeviceNum == 0:
            raise Exception("未找到设备!")
        
        if camera_index < 0 or camera_index >= device_list.nDeviceNum:
            raise Exception(f"无效的相机索引 {camera_index}, 可用索引 0 到 {device_list.nDeviceNum - 1}")

        print(f"找到 {device_list.nDeviceNum} 台设备，正在连接第 {camera_index} 台...")

        # 2. 创建句柄
        self.cam = MvCamera()
        st_device_info = cast(device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)).contents
        ret = self.cam.MV_CC_CreateHandle(st_device_info)
        if ret != MV_OK:
            raise Exception(f"创建句柄失败! ret[0x{ret:x}]")

        # 3. 打开设备
        ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != MV_OK:
            raise Exception(f"打开设备失败! ret[0x{ret:x}]")

        # 4. (仅 GigE) 探测最佳包大小
        if st_device_info.nTLayerType == MV_GIGE_DEVICE:
            n_packet_size = self.cam.MV_CC_GetOptimalPacketSize()
            if int(n_packet_size) > 0:
                ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", n_packet_size)
                if ret != MV_OK:
                    print(f"警告: 设置最佳包大小失败! ret[0x{ret:x}]")
            else:
                print(f"警告: 获取最佳包大小失败! ret[0x{n_packet_size:x}]")

        # 5. 设置触发模式为 Off (连续采集)
        ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        if ret != MV_OK:
            raise Exception(f"设置触发模式为 Off 失败! ret[0x{ret:x}]")

        # 6. 获取 Payload 大小并准备缓冲区
        st_param = MVCC_INTVALUE()
        memset(byref(st_param), 0, sizeof(MVCC_INTVALUE))
        ret = self.cam.MV_CC_GetIntValue("PayloadSize", st_param)
        if ret != MV_OK:
            raise Exception(f"获取 PayloadSize 失败! ret[0x{ret:x}]")
        
        self.payload_size = st_param.nCurValue
        # 缓冲区大小必须为 PayloadSize
        self.buffer = (c_ubyte * self.payload_size)()

        # 7. 开始取流
        ret = self.cam.MV_CC_StartGrabbing()
        if ret != MV_OK:
            raise Exception(f"开始取流失败! ret[0x{ret:x}]")
        
        self.is_open = True
        print(f"相机 {camera_index} 已成功打开并开始取流。")

    def read(self):
        """
        读取一帧图像
        :return: (bool, numpy.ndarray) (是否成功, 图像帧)
        """
        if not self.is_open:
            return False, None

        # 尝试获取一帧图像，超时时间 1000ms
        ret = self.cam.MV_CC_GetOneFrameTimeout(self.buffer, self.payload_size, self.frame_info, 1000)
        
        if ret == MV_OK:
            # --- 图像转换 ---
            # 我们需要将 c_ubyte * N 类型的 ctypes 缓冲区转换为 NumPy 数组
            # 注意: self.buffer 此时是一个 ctypes 数组
            
            # 检查像素格式
            pixel_type = self.frame_info.enPixelType
            width = self.frame_info.nWidth
            height = self.frame_info.nHeight

            # 创建一个正确大小的 NumPy 数组的 "视图"
            # （注意：如果使用 np.frombuffer，它会复制数据）
            # 我们需要根据数据实际长度来切片
            
            if pixel_type == PixelType_Gvsp_Mono8:
                # 1. 黑白图像
                image_data = self.buffer[:width * height]
                image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                return True, image
            
            elif pixel_type == PixelType_Gvsp_BGR8_Packed:
                # 2. BGR8 彩色图像
                image_data = self.buffer[:width * height * 3]
                image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width, 3))
                return True, image
            
            elif pixel_type == PixelType_Gvsp_BayerRG8:
                # 3. BayerRG8 格式，需要用 OpenCV 转换
                image_data = self.buffer[:width * height]
                raw_image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                color_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_RG2BGR)
                return True, color_image
            
            elif pixel_type == PixelType_Gvsp_BayerBG8:
                # 4. BayerBG8
                image_data = self.buffer[:width * height]
                raw_image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                color_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_BG2BGR)
                return True, color_image
            
            elif pixel_type == PixelType_Gvsp_BayerGB8:
                # 5. BayerGB8
                image_data = self.buffer[:width * height]
                raw_image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                color_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_GB2BGR)
                return True, color_image
            
            elif pixel_type == PixelType_Gvsp_BayerGR8:
                # 6. BayerGR8
                image_data = self.buffer[:width * height]
                raw_image = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                color_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_GR2BGR)
                return True, color_image
            
            else:
                # 其他格式暂不支持
                print(f"警告: 暂不支持的像素格式 [0x{pixel_type:x}]")
                return False, None
            # --- 转换结束 ---
        else:
            # print(f"读取帧失败! ret[0x{ret:x}]")
            return False, None

    def release(self):
        """
        释放相机资源
        """
        if not self.is_open:
            return

        print("正在释放相机...")
        # 停止取流
        self.cam.MV_CC_StopGrabbing()
        
        # 关闭设备
        self.cam.MV_CC_CloseDevice()
        
        # 销毁句柄
        self.cam.MV_CC_DestroyHandle()
        
        self.is_open = False
        self.cam = None
        self.buffer = None

    def __del__(self):
        # 析构函数，确保在对象被销毁时释放资源
        self.release()
    
    def __enter__(self):
        # 上下文管理器: 进入
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 上下文管理器: 退出
        self.release()

# --- 示例用法 ---
def main():
    
    # 1. 全局初始化 SDK
    ret = MvCamera.MV_CC_Initialize()
    if ret != MV_OK:
        print(f"SDK 初始化失败! ret[0x{ret:x}]")
        return

    cap = None
    try:
        # 2. 创建并打开相机
        # 使用 with 语句，自动管理 release
        with HikCamera(camera_index=0) as cap:
            
            print("相机已打开, 按 'q' 退出。")
            
            while True:
                # 3. 读取帧
                ret, frame = cap.read()
                
                if not ret:
                    print("读取帧失败")
                    break # 或者 continue
                
                # 4. (可选) 缩小图像以便显示
                h, w = frame.shape[:2]
                frame_small = cv2.resize(frame, (w // 2, h // 2))
                
                # 5. 显示图像
                cv2.imshow("Hikvision Camera", frame_small)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as e:
        print(f"发生错误: {e}")
    
    finally:
        # 6. 全局反初始化 SDK
        print("正在反初始化 SDK...")
        MvCamera.MV_CC_Finalize()
        cv2.destroyAllWindows()
        print("程序退出。")


if __name__ == "__main__":
    main()