import sys
from pathlib import Path
current_path = Path(__file__).resolve().parent.parent

import cv2
import numpy as np

def preprocess_image(img):
    # 1. 转灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. 降采样 (重要！)
    # 如果图片宽或高超过 2000 像素，检测器可能会因为噪点太多而失败
    # 我们将其限制在较合理的尺度，比如宽 1000-1500 左右
    height, width = gray.shape
    if width > 1500:
        scale = 1500 / width
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        # 注意：如果这里缩放了，最后算出来的 corners 坐标也要除以 scale 还原回去！
        print(f"图片过大，已缩放至: {gray.shape}")
    else:
        scale = 1.0

    # 3. CLAHE (限制对比度自适应直方图均衡化)
    # 这比普通的直方图均衡化更适合处理局部阴影
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)

    return gray, scale

def analyze_raw_pixel_sizes(img, pattern_size=(9, 6)):
    
    gray, scale = preprocess_image(img)

    # 使用 SB 算法 (更准)
    ret, corners = cv2.findChessboardCornersSB(gray, pattern_size, cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_ACCURACY)

    if not ret:
        print("未检测到棋盘格")
        return

    corners /= scale

    # corners 的形状是 (N, 1, 2)，为了方便处理，去掉中间那维 -> (N, 2)
    pts = corners.squeeze()
    
    cols, rows = pattern_size
    
    # 用来存储所有“横向相邻”格子的距离
    distances = []

    print(f"--- 开始分析 {cols}x{rows} 个角点 ---")

    # 遍历每一行
    for r in range(rows):
        for c in range(cols - 1): # 最后一列没有右边的邻居，所以减1
            index = r * cols + c
            
            p1 = pts[index]     # 当前点
            p2 = pts[index + 1] # 右边相邻点
            
            # 计算欧氏距离 (Pixels)
            dist = np.linalg.norm(p1 - p2)
            distances.append(dist)
            
            # 可视化：把距离写在图片上
            mid_point = (int((p1[0]+p2[0])/2), int((p1[1]+p2[1])/2))
            cv2.drawChessboardCorners(img, pattern_size, corners, ret)

    distances = np.array(distances)
    
    messages = []

    print(f"【分析结果】")
    print(f"最小格子宽度: {np.min(distances):.2f} px (通常是离镜头最远的)")
    print(f"最大格子宽度: {np.max(distances):.2f} px (通常是离镜头最近的)")
    print(f"平均格子宽度: {np.mean(distances):.2f} px")
    print(f"方差 (不均匀程度): {np.std(distances)/np.mean(distances):.2f}")
    
    messages.append(f"【分析结果】")
    messages.append(f"最小格子宽度: {np.min(distances):.2f} px (通常是离镜头最远的)")
    messages.append(f"最大格子宽度: {np.max(distances):.2f} px (通常是离镜头最近的)")
    messages.append(f"平均格子宽度: {np.mean(distances):.2f} px")
    messages.append(f"方差 (不均匀程度): {np.std(distances)/np.mean(distances):.2f}")

    if np.std(distances)/np.mean(distances) > 0.1:
        print("提示：方差较大，说明棋盘格存在明显的倾斜或旋转。")
        messages.append("提示：方差较大，说明棋盘格存在明显的倾斜或旋转。")
    
    return img, messages, np.mean(distances)

if __name__ == "__main__":

    import matplotlib.pyplot as plt

    test_image_folder = current_path.parent / "test" / "calibration"

    img_path = test_image_folder / "IMG_1091-1.jpg"

    img = cv2.imread(str(img_path))

    result = analyze_raw_pixel_sizes(img, pattern_size=(11, 8))

    if result: # not None
        img_labeled, messages, size = result
    
    plt.figure(dpi=300)
    plt.imshow(img_labeled)
    plt.show()