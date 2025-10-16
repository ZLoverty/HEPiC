"""
vision.py
=========
Implement die swell detection and other vision related needs.
"""

import cv2
import numpy as np
from skimage.morphology import skeletonize
from myimagelib import to8bit
from skan import Skeleton, summarize
import time
from PySide6.QtCore import QObject, Signal, Slot
from collections import deque
import os
import glob

def filament_diameter(img):
    """Calculate the diameter of a filament in an image. 
    The filament is assumed to be brighter than the background.
    The method uses distance transform and skeletonization to estimate the diameter.
    
    Parameters:
    -----------
    img : np.ndarray
        Input image containing the filament.
        
    Returns:
    --------
    diameter: float
        Estimated diameter of the filament in pixels.
    skeleton: np.ndarray
        Binary image of the filament skeleton. For visualization purpose.
    dist_transform: np.ndarray
        Gray scale image showing distance transform results. 
    """

    assert img.ndim == 2, "Input image must be grayscale"

    img = to8bit(img) # convert to 8-bit if necessary, maximaize the contrast

    blur = cv2.GaussianBlur(img, (5, 5), 0)

    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)

    skeleton = skeletonize(binary)

    diameter = dist_transform[skeleton].mean() * 2

    return diameter, skeleton, dist_transform

def convert_to_grayscale(img):
    """
    Converts an image to grayscale.

    Parameters
    ----------
    img : np.ndarray
        Either a string representing the path to an image file, or a numpy array (OpenCV image).

    Returns
    -------
    np.ndarray
        A numpy array representing the grayscale image, or None if conversion fails.
    """

    # Check if the image already has only 2 dimensions (meaning it's already grayscale)
    # or if it has 3 channels (most common color image format)
    if len(img.shape) == 2:
        # print("Image is already grayscale.")
        return img # It's already grayscale, no conversion needed

    if len(img.shape) == 3:
        # Check the number of channels to determine the correct conversion code
        # Most common: BGR (3 channels) or BGRA (4 channels with alpha)
        channels = img.shape[2]
        if channels == 3:
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif channels == 4:
            # If it has an alpha channel, convert from BGRA to GRAY
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            print(f"Warning: Image has {channels} channels, which is unusual for a color image. Attempting BGR to GRAY.")
            # Fallback, might not be accurate if the channel order is non-standard
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) 
    else:
        print(f"Error: Unsupported image shape: {img.shape}. Cannot convert to grayscale.")
        return None
        
    return gray_img

def draw_filament_contour(img, skeleton, diameter):
    """Draw the contour of the filament based on its skeleton and diameter.
    
    Parameters:
    -----------
    img : np.ndarray
        Input image containing the filament.
    skeleton: np.ndarray
        Binary image of the filament skeleton.
    diameter: float
        Estimated diameter of the filament in pixels.
        
    Returns:
    --------
    contour_img: np.ndarray
        Image with the filament contour drawn.
    """
    reconstructed_mask = np.zeros_like(img, dtype=np.uint8)
    
    # Find coordinates of skeleton points
    y_coords, x_coords = np.where(skeleton)
    
    for (x, y) in zip(x_coords, y_coords):
        center = (x, y) # OpenCV坐标是(x, y)
        
        # 绘制白色的实心圆 (颜色255, thickness=-1表示填充)
        try:
            cv2.circle(reconstructed_mask, center, int(round(diameter//2)), 255, thickness=-1)
        except ValueError as e:
            return img
        except Exception as e:
            print(f"未知错误: {e}")

    contours, _ = cv2.findContours(reconstructed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_rgb = cv2.cvtColor(cv2.cvtColor(to8bit(img), cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2RGB)

    labeled_image = cv2.drawContours(img_rgb.copy(), contours, -1, (255, 0, 0), 2)

    return labeled_image

def find_longest_branch(skeleton):
    """Find the longest branch in a skeleton image (binary).
    If no skeleton is present, return the original image.
    
    Parameters
    ----------
    skeleton : nd.array
        skeleton image
    
    Returns
    -------
    nd.array
        the longest branch label image
    """
    try:
        skel_obj = Skeleton(skeleton)
    except ValueError as e:
        print(f"ValueError: {e}")
        return None
    
    branch_data = summarize(skel_obj, separator="_") # analyze the branches in the skeleton

    long_branch_id = branch_data["branch_distance"].argmax() + 1 # find the id of the longest branch (it's the data index + 1)

    branch_labels = skel_obj.path_label_image() # get path label image where locations of skeleton are labeled

    longest_branch = (branch_labels == long_branch_id) # find where label == the id

    return longest_branch

class ImageStreamer:
    """
    一个模拟 cv2.VideoCapture 的类，用于从一系列静态图片创建一个视频流。Simulate a video stream to test the filament detection module. This script makes use of a few filament detection test images, basically send them over to a buffer at a specified rate and let the main process access the images. Note that the `ImageStreamer` class can be directly replaced by cv2.VideoCapture in production.
    """
    def __init__(self, image_folder, fps=30, loop=True):
        """
        初始化
        :param image_folder: 包含图片的文件夹路径
        :param fps: 模拟的帧率
        :param loop: 是否循环播放
        """
        self.image_folder = image_folder
        self.fps = fps
        self.loop = loop
        
        # 获取并排序图片文件
        self.image_files = sorted(glob.glob(os.path.join(self.image_folder, '*.[pP][nN][gG]')) + 
                                  glob.glob(os.path.join(self.image_folder, '*.[jJ][pP][gG]')) +
                                  glob.glob(os.path.join(self.image_folder, '*.[jJ][pP][eE][gG]')))
        
        if not self.image_files:
            raise FileNotFoundError(f"No images found in the directory: {self.image_folder}")

        self.num_frames = len(self.image_files)
        self.current_frame_index = 0
        self._is_opened = True

    def isOpened(self):
        """模拟 isOpened() 方法。"""
        if self.loop:
            return self._is_opened 
        else:
            return self._is_opened and self.current_frame_index < self.num_frames

    def read(self):
        """
        模拟 read() 方法。
        返回一个元组 (success, frame)。
        """
        if not self.isOpened():
            return (False, None)

        # 获取当前帧的路径
        image_path = self.image_files[self.current_frame_index]
        frame = cv2.imread(image_path)
        
        if frame is None:
            # 读取失败
            print(f"Warning: Failed to read {image_path}")
            # 尝试移动到下一帧
            self.current_frame_index += 1
            if self.loop:
                self.current_frame_index %= self.num_frames
            return self.read() # 递归调用以获取下一个有效帧

        # 移动到下一帧
        self.current_frame_index += 1
        
        # 处理循环
        if self.loop and self.current_frame_index >= self.num_frames:
            self.current_frame_index = 0
            
        return (True, frame)

    def release(self):
        """模拟 release() 方法。"""
        self._is_opened = False
        self.current_frame_index = 0
        self.image_files = []

    def get(self, propId):
        """模拟 get() 方法，可以返回FPS等信息。"""
        if propId == cv2.CAP_PROP_FPS:
            return self.fps
        # 可以根据需要添加其他属性
        return None

if __name__ == "__main__":
    # an example showing the two step approach 
    from pathlib import Path
    import matplotlib.pyplot as plt

    folder = Path("../test/filament_images_simulated")
    img = cv2.imread(folder / "curly_50px.png", cv2.IMREAD_GRAYSCALE)
    diameter, skeleton, dist_transform = filament_diameter(img) # the rough estimate
    print(f"Rough estimate: {diameter} px")
    longest_branch = find_longest_branch(skeleton)
    diameter_refine = dist_transform[longest_branch].mean() * 2.0
    print(f"Refined: {diameter_refine}")

    fig, ax = plt.subplots(ncols=2, figsize=(10, 5), dpi=100)
    label_rough = draw_filament_contour(img, skeleton, diameter)
    label_refine = draw_filament_contour(img, longest_branch, diameter_refine)
    ax[0].imshow(label_rough)
    ax[1].imshow(label_refine)