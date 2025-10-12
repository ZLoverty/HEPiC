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
        cv2.circle(reconstructed_mask, center, int(round(diameter//2)), 255, thickness=-1)

    contours, _ = cv2.findContours(reconstructed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_rgb = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2RGB)

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
        return skeleton
    
    branch_data = summarize(skel_obj) # analyze the branches in the skeleton

    long_branch_id = branch_data["branch-distance"].argmax() + 1 # find the id of the longest branch (it's the data index + 1)

    branch_labels = skel_obj.path_label_image() # get path label image where locations of skeleton are labeled

    longest_branch = (branch_labels == long_branch_id) # find where label == the id

    return longest_branch

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