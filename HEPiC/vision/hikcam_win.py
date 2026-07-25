import sys
import os
import logging
import numpy as np
import cv2
from ctypes import *
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保 MvImport 路径正确，并尝试导入 SDK
CAM_LIB_LOADED = False
sdk_path = None
try:
    if os.name == 'nt':  # Windows
        sdk_path = str(Path(os.getenv('MVCAM_COMMON_RUNENV')) / "Samples" / "Python" / "MvImport")
        os.add_dll_directory(r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64")
    else:  # Linux/Mac
        sdk_path = "/opt/MVS/Samples/Python/MvImport"
    sys.path.append(sdk_path)
    from MvCameraControl_class import *
    CAM_LIB_LOADED = True
except Exception as e:
    logger.error(f"相机 SDK 加载失败，相机将不可用。SDK 路径: {sdk_path}，错误: {e}")
    CAM_LIB_LOADED = False


class HikCameraError(Exception):
    """Hikvision 相机操作相关的错误"""
    pass


class HikVideoCapture:
    """
    主动设置参数的、高效的 Hikvision 相机封装类

    用法:
        MvCamera.MV_CC_Initialize()
        try:
            # 主动设定为 BGR8 格式
            cap = HikVideoCapture(camera_index=0, pixel_format=PixelType_Gvsp_BGR8_Packed)

            # 或者让它自动使用相机的默认格式 (Mono8)
            # cap = HikVideoCapture(camera_index=0)

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

    def __init__(self, camera_index=0, width: int | None = None, height: int | None = None,
                 exposure_time: float | None = None, center_roi: bool = True,
                 pixel_format: int | None = None):

        if not CAM_LIB_LOADED:
            raise HikCameraError("相机 SDK 未成功加载，无法创建相机对象。")

        self.cam = None
        self.buffer = None
        self.payload_size = 0
        self.is_open = False

        # --- 图像转换参数 (将在 _set_camera_props 中被赋值) ---
        self.img_width = 0
        self.img_height = 0
        self.img_bpp = 1  # 默认为1 (Mono8)
        self.conversion_code = None  # OpenCV 转换码

        try:
            # 1. 枚举设备
            device_list = self._enum_devices()
            if device_list.nDeviceNum == 0:
                raise HikCameraError("未找到设备!")
            if camera_index >= device_list.nDeviceNum:
                raise HikCameraError(f"无效的相机索引 {camera_index}")

            # 2. 创建句柄
            self.cam = MvCamera()
            st_device_info = cast(device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)).contents
            ret = self.cam.MV_CC_CreateHandle(st_device_info)
            if ret != MV_OK:
                raise HikCameraError(f"创建句柄失败! ret[0x{ret:x}]")

            # 3. 打开设备
            ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                logger.error("请检查电脑和相机是否在同段IP。")
                raise HikCameraError(f"打开设备失败! ret[0x{ret:x}]")
            self.is_open = True  # 标记为已打开，以便后续步骤和 release() 可以工作

            # 4. (仅 GigE) 探测最佳包大小
            if st_device_info.nTLayerType == MV_GIGE_DEVICE:
                self._optimize_gige_packet_size()

            # 5. 设置触发模式为 Off (连续采集)
            ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            if ret != MV_OK:
                raise HikCameraError(f"设置触发模式为 Off 失败! ret[0x{ret:x}]")

            # ==========================================================
            # 6. 【核心】主动设置或获取相机参数
            # ==========================================================
            # 设置像素格式 (未指定时默认使用 Mono8)
            requested_pixel_format = pixel_format if pixel_format is not None else PixelType_Gvsp_Mono8
            ret = self.cam.MV_CC_SetEnumValue("PixelFormat", requested_pixel_format)
            if ret != MV_OK:
                raise HikCameraError(f"设置像素格式失败! ret[0x{ret:x}]。 确保相机支持该格式。")

            self._set_camera_props(width, height)

            if center_roi:
                try:
                    width_max = self._get_int_value("WidthMax")
                    height_max = self._get_int_value("HeightMax")

                    # 使用整数除法计算偏移量，基于相机实际生效的分辨率
                    offset_x = (width_max - self.img_width) // 2
                    offset_y = (height_max - self.img_height) // 2

                    logger.info(f"传感器最大分辨率: {width_max}x{height_max}。正在计算居中偏移...")

                    ret = self.cam.MV_CC_SetIntValue("OffsetX", offset_x)
                    if ret == MV_OK:
                        logger.info(f"成功设置 OffsetX 为: {offset_x}")
                    else:
                        logger.warning(f"设置 OffsetX {offset_x} 失败! ret[0x{ret:x}]")

                    ret = self.cam.MV_CC_SetIntValue("OffsetY", offset_y)
                    if ret == MV_OK:
                        logger.info(f"成功设置 OffsetY 为: {offset_y}")
                    else:
                        logger.warning(f"设置 OffsetY {offset_y} 失败! ret[0x{ret:x}]")

                except Exception as e:
                    logger.warning(f"自动居中ROI时出错: {e}。ROI可能未居中。")

            # 7. 获取 Payload 大小并准备缓冲区
            self.payload_size = self._get_int_value("PayloadSize")
            if self.payload_size == 0:
                raise HikCameraError("获取 PayloadSize 失败!")

            # 缓冲区大小必须为 PayloadSize
            self.buffer = (c_ubyte * self.payload_size)()
            self.frame_info = MV_FRAME_OUT_INFO_EX()

            # 关闭自动曝光
            ret = self.cam.MV_CC_SetEnumValueByString("ExposureAuto", "Off")
            if ret != MV_OK:
                logger.warning(f"关闭自动曝光失败! ret[0x{ret:x}]")
            else:
                logger.info("自动曝光已关闭 (ExposureAuto -> Off)")

            # 手动设置曝光时间 (单位：微秒 μs)
            if exposure_time is not None:
                exposure_time_us = 1000.0 * exposure_time  # 传入单位为 ms，转换为 us
                ret = self.cam.MV_CC_SetFloatValue("ExposureTime", exposure_time_us)
                if ret != MV_OK:
                    logger.warning(f"设置曝光时间失败! ret[0x{ret:x}]")
                else:
                    logger.info(f"曝光时间已设置为: {exposure_time_us} μs")

            # 8. 开始取流
            ret = self.cam.MV_CC_StartGrabbing()
            if ret != MV_OK:
                raise HikCameraError(f"开始取流失败! ret[0x{ret:x}]")

            logger.info(f"相机 {camera_index} 已打开。")
            logger.info(f"  -> 分辨率: {self.img_width}x{self.img_height}")

        except Exception:
            # 初始化过程中任何一步失败，都尝试释放已经拿到的相机资源，避免句柄/设备泄漏
            self.release()
            raise

    def _enum_devices(self):
        device_list = MV_CC_DEVICE_INFO_LIST()
        tlayer_type = MV_GIGE_DEVICE | MV_USB_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(tlayer_type, device_list)
        if ret != MV_OK:
            raise HikCameraError(f"枚举设备失败! ret[0x{ret:x}]")
        return device_list

    def _optimize_gige_packet_size(self):
        n_packet_size = self.cam.MV_CC_GetOptimalPacketSize()
        if int(n_packet_size) > 0:
            ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", n_packet_size)
            if ret != MV_OK:
                logger.warning(f"设置最佳包大小失败! ret[0x{ret:x}]")
        else:
            logger.warning(f"获取最佳包大小失败! ret[0x{n_packet_size:x}]")

    def _get_int_value(self, key):
        st_param = MVCC_INTVALUE()
        memset(byref(st_param), 0, sizeof(MVCC_INTVALUE))
        ret = self.cam.MV_CC_GetIntValue(key, st_param)
        if ret != MV_OK:
            raise HikCameraError(f"获取参数 '{key}' 失败! ret[0x{ret:x}]")
        return st_param.nCurValue

    def _get_enum_value(self, key):
        st_param = MVCC_ENUMVALUE()
        memset(byref(st_param), 0, sizeof(MVCC_ENUMVALUE))
        ret = self.cam.MV_CC_GetEnumValue(key, st_param)
        if ret != MV_OK:
            raise HikCameraError(f"获取参数 '{key}' 失败! ret[0x{ret:x}]")
        return st_param.nCurValue

    def _set_camera_props(self, width, height):
        """主动设置或获取参数，并设置内部转换变量"""

        # 设置宽度 (如果提供了)
        if width is not None:
            ret = self.cam.MV_CC_SetIntValue("Width", width)
            if ret != MV_OK:
                raise HikCameraError(f"设置宽度失败! ret[0x{ret:x}]。")

        # 设置高度 (如果提供了)
        if height is not None:
            ret = self.cam.MV_CC_SetIntValue("Height", height)
            if ret != MV_OK:
                raise HikCameraError(f"设置高度失败! ret[0x{ret:x}]。")

        # 【关键】获取最终的实际参数
        self.img_width = self._get_int_value("Width")
        self.img_height = self._get_int_value("Height")
        self.pixel_format_int = self._get_enum_value("PixelFormat")

        # 根据最终的像素格式，预先设置好转换参数
        if self.pixel_format_int == PixelType_Gvsp_Mono8:
            self.img_bpp = 1
            self.conversion_code = None  # Mono8 无需转换
        elif self.pixel_format_int == PixelType_Gvsp_BGR8_Packed:
            self.img_bpp = 3
            self.conversion_code = None  # BGR8 无需转换
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
            raise HikCameraError(f"不支持的像素格式! [0x{self.pixel_format_int:x}]")

    def read(self):
        """
        高效读取一帧图像。
        使用 __init__ 中设置好的转换参数，按需将 Bayer 图像转换为 BGR。
        """
        if not self.is_open:
            return False, None

        # 尝试获取一帧图像，超时 1000ms
        ret = self.cam.MV_CC_GetOneFrameTimeout(self.buffer, self.payload_size, self.frame_info, 1000)

        if ret != MV_OK:
            logger.debug(f"读取帧失败! ret[0x{ret:x}]")
            return False, None

        # 1. 计算有效数据长度 (防止缓冲区末尾有无效数据)
        data_len = self.img_width * self.img_height * self.img_bpp

        # 2. 将 ctypes 缓冲区转换为 NumPy 数组
        image_data = self.buffer[:data_len]
        image = np.frombuffer(bytes(image_data), dtype=np.uint8)

        if self.img_bpp == 1:
            image = image.reshape(self.img_height, self.img_width)
        else:
            image = image.reshape(self.img_height, self.img_width, self.img_bpp)

        # 3. 按需做颜色空间转换 (例如 Bayer -> BGR)
        if self.conversion_code is not None:
            image = cv2.cvtColor(image, self.conversion_code)

        return True, image

    def release(self):
        if self.cam is None:
            return

        logger.info("正在释放相机...")

        if self.is_open:
            ret = self.cam.MV_CC_StopGrabbing()
            if ret != MV_OK:
                logger.warning(f"停止取流失败! ret[0x{ret:x}]")

            ret = self.cam.MV_CC_CloseDevice()
            if ret != MV_OK:
                logger.warning(f"关闭设备失败! ret[0x{ret:x}]")

        ret = self.cam.MV_CC_DestroyHandle()
        if ret != MV_OK:
            logger.warning(f"销毁句柄失败! ret[0x{ret:x}]")

        self.is_open = False
        self.cam = None
        self.buffer = None

    def __del__(self):
        # 解释器退出阶段模块级符号可能已被清空，release() 内部调用可能失败，
        # 这里仅做 best-effort 清理，不应该让异常从析构函数中抛出。
        try:
            self.release()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# --- 示例用法 ---
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ret = MvCamera.MV_CC_Initialize()
    if ret != MV_OK:
        logger.error(f"SDK 初始化失败! ret[0x{ret:x}]")
        return

    try:
        # === 示例 1: 主动设置为 Mono8 (默认), 512x512 ===
        logger.info("--- 正在尝试以默认 (Mono8) 模式打开 ---")
        cap = HikVideoCapture(
            camera_index=0,
            width=512,
            height=512,
            exposure_time=30000
        )

        # === 示例 2: 主动设置为 BGR8 ===
        # (确保你的相机支持 BGR8，否则会抛出异常)
        # cap = HikVideoCapture(
        #     camera_index=0,
        #     width=640,
        #     height=480,
        #     pixel_format=PixelType_Gvsp_BGR8_Packed
        # )

        # === 示例 3: 使用相机当前默认设置 ===
        # cap = HikVideoCapture(camera_index=0)

        with cap:
            logger.info("相机已打开, 按 'q' 退出。")

            while True:
                ret, frame = cap.read()

                if ret:
                    cv2.imshow("Hikvision Camera Pro", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as e:
        logger.error(f"发生错误: {e}", exc_info=True)

    finally:
        logger.info("正在反初始化 SDK...")
        MvCamera.MV_CC_Finalize()
        cv2.destroyAllWindows()
        logger.info("程序退出。")


if __name__ == "__main__":
    main()
