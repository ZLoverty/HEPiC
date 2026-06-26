# 红外页

红外页（`IRPageWidget`）承载 Optris 热成像仪的实时热像画面、温度量程选择、对焦调节与 ROI 框选，并持续检测口模出口处的熔体温度。

![红外页整体截图](../images/ir-page.png)

---

## 实时热像画面

**白话**：页面主体显示 Optris 热成像仪拍摄的实时热像图。颜色代表温度分布，通常越亮/越暖色表示温度越高。在画面上按住鼠标左键拖拽可框选感兴趣区域（ROI），松开鼠标即生效；在画面空白处拖拽会替换现有 ROI 框。ROI 框四角有缩放句柄可调整大小。

**技术说明**：对应 `IRPageWidget.image_widget`（`VisionWidget` 实例，模式固定为 `"roi"`）。`IRWorker` 在独立线程中每 30 ms 读一次热像帧（`OptrisCamera.read()`）与温度矩阵（`OptrisCamera.read_temp()`）；`MainWindow._refresh_displays()` 定时器调用 `ir_worker.get_latest_frame()` 后通过 `image_widget.update_live_display(frame)` 刷新显示。鼠标释放时 `VisionWidget.on_roi_changed()` 发出 `sigRoiChanged(x, y, w, h)` 信号，连接到 `IRWorker.set_roi`，后续帧将仅在该区域内计算最高温度。

---

## 控制栏

控制栏位于热像画面上方，由温度量程下拉菜单和对焦滑条左右排列组成。

---

### 温度量程

**白话**：通过此下拉菜单选择 Optris 热成像仪的工作量程（例如 `-20 – 100 °C`、`0 – 250 °C`、`150 – 900 °C`）。量程越小，温度分辨率越高，读数越精准；量程越大，覆盖范围越广，但精度相对较低。请根据实验中熔体的实际温度区间选择合适量程。

**技术说明**：`mode_menu`（`QComboBox`）。程序启动时调用 `OptrisCamera.list_available_ranges(0)` 枚举相机支持的量程，每条量程格式化为 `"{min_temp} - {max_temp}"` 后添加到菜单。`currentIndexChanged(int)` 信号连接到 `IRWorker.set_range(range_index)`：`set_range` 先停止采集定时器，释放当前 `OptrisCamera` 对象，然后以新的 `temp_range_index` 重新实例化 `OptrisCamera`，完成后恢复定时器。因此**切换量程会短暂中断画面**，这是正常现象。

---

### 对焦滑条

**白话**：拖动此水平滑条可调整热成像仪的对焦位置（取值范围 0–100）。若热像画面边缘模糊或中心区域不清晰，可微调此滑条直到画面最清晰为止。

**技术说明**：`focus_bar`（`QScrollBar`，水平方向，最小值 0，最大值 100）。`valueChanged(int)` 信号连接到 `IRWorker.set_position(position)`，`set_position` 调用 `OptrisCamera.set_focus(position)`，将对焦值传递给底层 Optris SDK。

---

## ROI 框选

**白话**：在热像画面上拖拽鼠标，可框选一块矩形 ROI，用于限定熔体出口温度的检测范围。ROI 设置后，温度检测将仅统计该区域内的最高温度，排除背景干扰。若不框选，默认使用整幅画面中的最高温度。

**技术说明**：ROI 交互由 `VisionWidget`（`image_widget`）负责，见上文"实时热像画面"部分。`IRWorker.set_roi(roi)` 接收 `(x, y, w, h)` 元组后保存为 `self.roi`；`read_one_frame()` 中若 `self.roi` 不为 `None`，则使用切片 `frame[y:y+h, x:x+w]` 和 `temps[y:y+h, x:x+w].max()` 分别更新裁剪帧与最高温度；若 `self.roi` 为 `None`，则取全幅最高温度（`temps.max()`）。

---

## 口模出口温度（`die_temperature_C`）

**白话**：软件持续读取 ROI 区域内温度矩阵的最大值，作为口模出口处熔体温度的实时估计值（°C）。该数值会同步显示在主页状态面板的"出口熔体温度"一行，并记录到 CSV 数据文件的 `die_temperature_C` 列中。

**技术说明**：`IRWorker.die_temperature`（`float`，初始为 `np.nan`）在每次成功读帧（`ret_img and ret_temp` 均为 `True`）后更新。若设有 ROI，值为 `temps[y:y+h, x:x+w].max()`；否则为 `temps.max()`。主循环通过 `MainWindow.grab_status()` 读取此值并写入 `data_status["die_temperature_C"]`。若热成像仪断线或读帧失败，值保持 `np.nan`，状态面板显示 `--`。
