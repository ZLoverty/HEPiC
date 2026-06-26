# 视觉页

视觉页（`VisionPageWidget`）承载 Hikrobot 工业相机的实时画面、ROI 框选与曝光控制，并在后台持续检测挤出口模熔体直径。

![视觉页整体截图](../images/vision-page.png)

---

## 实时相机画面（左侧视图）

**白话**：左侧大图实时显示 Hikrobot 工业相机拍到的全幅画面。在画面上按住鼠标左键并拖拽，即可框选一块感兴趣区域（ROI）；松开鼠标后 ROI 即生效。ROI 框的四角有缩放句柄，可拖动调整大小；若想重新框选，在画面空白处拖拽即可自动替换旧框。

**技术说明**：对应 `VisionPageWidget.vision_widget`（`VisionWidget` 实例，模式固定为 `"roi"`）。画面由 `VideoWorker` 在独立线程中每 10 ms 读一次最新帧；`MainWindow._refresh_displays()` 定时器（间隔 `1000 / fps` ms）调用 `video_worker.get_latest_frame()` 后通过 `update_live_display(frame)` 刷新显示。鼠标释放后 `VisionWidget.on_roi_changed()` 发出 `sigRoiChanged(x, y, w, h)` 信号，连接到 `VideoWorker.set_roi`，使后续裁剪在后台完成。

---

## ROI 结果视图（右侧视图）

**白话**：右侧小图显示左侧 ROI 框选区域经过图像处理后的结果——包括二值化、骨架提取，以及叠加到灰度图上的熔体轮廓线。这是软件实际用于计算熔体直径的图像。

**技术说明**：对应 `VisionPageWidget.roi_vision_widget`（`VisionWidget` 实例）。`VideoWorker.roi_frame_signal` 把裁剪后的帧送入 `ProcessingWorker.add_frame_to_queue`；`ProcessingWorker.process_frame()` 执行 CLAHE 增强 → 二值化 → 距离变换/骨架检测 → 绘制轮廓，最终通过 `proc_frame_signal` 把处理帧传给 `roi_vision_widget.update_live_display()`。

---

## 控制面板

控制面板位于页面左侧，宽度固定为 200 px，包含以下控件。

---

### 曝光时间

**白话**：在"曝光时间"输入框中输入数值（单位 ms），按 Enter 键即刻生效。曝光时间越长，画面越亮，但快速运动的熔体可能出现模糊；曝光时间越短，画面越暗，适合高速丝材。默认值为 50 ms。

**技术说明**：`exp_time`（`QLineEdit`，最大宽度 30 px，默认值 `"50"`）。按 Enter 触发 `on_exp_time_pressed()`，将文本解析为 `float` 后通过 `sigExpTime` 信号发送给 `VideoWorker.set_exp_time(exp_time)`。`set_exp_time` 会先释放当前相机对象，再以新的 `exposure_time=exp_time*1000`（转换为 μs）重新实例化 `HikVideoCapture`。

---

### FPS（帧率）

**白话**：在"FPS"输入框中输入帧率数字，按 Enter 键即刻更改相机取帧频率。默认值为 10 帧/秒。降低帧率可减少 CPU 负担；提高帧率可获得更流畅的画面，但对计算机性能要求更高。

**技术说明**：`fps`（`QLineEdit`，默认值 `"10"`）。按 Enter 触发 `on_fps_pressed()`，将文本解析为 `float` 后通过 `sigFPS` 信号发送给 `VideoWorker.set_fps(fps)`。`set_fps` 重置定时器步长为 `1000 / fps` ms，显示刷新计时器也相应更新。

---

### 黑白反转

**白话**：勾选"黑白反转"后，图像处理算法会对二值图像取反，即把白色熔体识别为黑色背景。若熔体颜色比背景深（例如深色耗材在亮背景前拍摄），通常需要勾选此选项，否则直径检测会失败。

**技术说明**：`invert_button`（`QCheckBox`，标签"黑白反转"）。`toggled(bool)` 信号连接到 `ProcessingWorker.invert_toggle(checked)`，将 `self.invert` 设为 `checked`。在 `process_frame()` 中，若 `self.invert is True`，则执行 `cv2.bitwise_not(binary)` 后再进行骨架检测。

---

### 棋盘校准

**白话**：点击"棋盘校准"按钮，弹出校准对话框。在对话框内对棋盘格图像上已知长度的格子画一条测量线，输入实际尺寸（mm），点击"校准"，软件会计算出每像素对应的实际尺寸（mm/px）并存入系统，供后续将 `die_diameter_px` 换算为毫米使用。

**技术说明**：`calibration_button`（`QPushButton`，标签"棋盘校准"）。点击触发 `on_calibration_pressed()`：实例化 `CalibrationDialog`（对话框内置一个 `"measure"` 模式的 `VisionWidget`，支持拉线段 ROI），将当前帧通过 `sigCapturedFrame` 发送到对话框；用户确认后调用 `dialog.get_mpp()` 取得 mm/px 值，通过 `sigMPP` 信号发出，供主程序保存。

---

## 熔体直径检测（`die_diameter_px`）

**白话**：软件会持续对 ROI 视图中的画面做分析，自动检测熔体从口模挤出后的直径（以像素为单位）。检测结果会同步显示在主页状态面板的"出口熔体直径"一行，并记录到 CSV 数据文件的 `die_diameter_px` 列中。

**技术说明**：`ProcessingWorker.die_diameter` 在每次成功的 `process_frame()` 调用后更新。流程为：灰度化 → 8 bit 转换 → CLAHE 增强 → Otsu 二值化（可选黑白反转）→ 距离变换（`cv2.distanceTransform`）→ 骨架提取（`skimage.morphology.skeletonize`）→ 对骨架像素的距离变换值求均值后乘以 2.0，得到 `diameter_refine`（像素），赋值给 `self.die_diameter`。主循环通过 `MainWindow.grab_status()` 读取此值并写入 `data_status["die_diameter_px"]`。若图像无法处理（如纯色），`die_diameter` 保持 `np.nan`。

!!! note "记录期间 ROI 框选被禁用"
    点击播放/记录按钮开始数据采集后，左侧视图的鼠标模式会自动切换为 `"view"`（只读），防止意外修改 ROI 区域。停止记录后恢复为 `"roi"` 模式。
