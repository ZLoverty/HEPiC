# 主页

主页是 HEPiC 的核心操作界面，连接成功后自动显示。左侧为手动操作与控制区，右侧为实时数据监视区。

![主页整体截图](../images/home-page.png)

---

## 状态面板

![状态面板截图](../images/home-status-panel.png)

状态面板（`PlatformStatusWidget`）固定宽度显示在右侧区域左上角，汇总当前平台的关键运行参数。

---

### 温度行（实测 / 目标）

**白话**：显示热端当前温度和你设定的目标温度，格式为"实测值 / 目标值"。旁边有一个输入框，输入数字后按 Enter 即可修改目标温度。

**技术说明**：`hotend_temperature_value`（`QLabel`）显示实测温度，读取数据字典中的 `measured_temperature_C` 键（其上游由 Klipper 的 `extruder.temperature` 映射而来）。`hotend_temperature_input`（`QLineEdit`，最大宽度 60 px）接收用户输入，按 Enter 触发 `on_temp_enter_pressed`，通过 `set_temperature` 信号发送给 `KlipperWorker.set_temperature`，下发 `M104 S{value}` G-code。

---

### 进线速度行（实测 / 设定）

**白话**：第一个数字是编码器实测到的丝材进线速度，第二个数字是 Klipper 当前的挤出速度设定值，单位均为 mm/s。两者接近说明平台运行正常。

**技术说明**：`measured_feedrate_value`（`QLabel`）显示来自 TCP 传感器的 `measured_feedrate_mms`；`feedrate_value`（`QLabel`）显示来自 Klipper `motion_report.live_extruder_velocity` 的 `feedrate_mms`。两者均由 `update_display(data)` 槽刷新。

---

### TCP 传感器行（动态）

**白话**：连接后，平台会告诉软件它装了哪些传感器（如挤出力、计米数等），状态面板会自动为每个传感器添加一行，显示实时读数。部分传感器旁边有一个小图标按钮，点击可将该传感器归零。

**技术说明**：调用 `configure_tcp_sensors(sensor_names, zeroable_sensor_names, sensor_labels)` 动态创建行布局。可归零传感器对应的行会添加一个带 `toZero.png` 图标的 `QPushButton`，点击后触发 `zero_sensor(name)` 信号，由 `TCPClient.zero_sensor` 槽处理。

---

### 出口熔体直径（可选）

**白话**：若 Hikrobot 工业相机初始化成功，此行显示视觉模块检测到的口模熔体直径（像素值）。

**技术说明**：`die_diameter_value`（`QLabel`）默认隐藏（`setVisible(False)`），相机初始化成功后由 `set_die_diameter_visible(True)` 显示。数值来自 `DataProcessorWidget` 检测结果，通过 `die_diameter_px` 字段更新。

---

### 出口熔体温度（可选）

**白话**：若 Optris 红外热像仪初始化成功，此行显示红外 ROI 区域内的熔体出口温度（°C）。

**技术说明**：`die_temperature_value`（`QLabel`）默认隐藏，红外仪初始化成功后由 `set_die_temperature_visible(True)` 显示。数值来自 `IRWorker.die_temperature`，字段名 `die_temperature_C`。

---

### 任务进度条

**白话**：运行 G-code 任务文件时，进度条显示整体完成百分比，旁边会显示预计完成时间（格式如"预计 15:30 完成"）。

**技术说明**：`progress_bar`（`QProgressBar`，范围 0–100）由 `update_progress(progress)` 槽驱动，`progress` 来自 Klipper 的 `virtual_sdcard.progress`。`_eta_str()` 根据已用时间线性估算剩余时间，进度低于 1% 或刚启动（不足 5 秒）时不显示预计时间。

---

## 模口膨胀 ROI 视图

![模口膨胀 ROI 视图截图](../images/home-dieswell-roi.png)

**白话**：此区域显示 Hikrobot 工业相机拍到的口模区域裁剪图，用于实时观察丝材从口模挤出后的膨胀状态。

**技术说明**：对应 `HomeWidget.dieswell_widget`（`VisionWidget` 实例）。`_refresh_displays()` 定时器每帧从 `ProcessingWorker.get_latest_proc_frame()` 取最新的处理帧并调用 `dieswell_widget.update_live_display(frame)`。仅在相机初始化成功后有实时画面；无相机时显示为空白占位区。

---

## 红外 ROI 视图

![红外 ROI 视图截图](../images/home-ir-roi.png)

**白话**：此区域显示红外热像仪对准口模区域的热成像裁剪图，颜色越亮表示温度越高，帮助你直观判断熔体出口温度分布。

**技术说明**：对应 `HomeWidget.ir_roi_widget`（`VisionWidget` 实例）。定时器从 `IRWorker.get_latest_roi_frame()` 取裁剪后的红外帧并调用 `ir_roi_widget.update_live_display(ir_roi)`。仅在红外热像仪初始化成功后有实时画面。

---

## 实时数据曲线图

![实时数据曲线图截图](../images/home-data-plot.png)

**白话**：连接后，所有传感器的实时数值会在此区域以时间为横轴绘制成折线图。每个传感器对应一张图表，图表上方有复选框，勾选或取消勾选可控制哪些传感器显示、哪些隐藏，方便专注观察你关心的数据。

**技术说明**：对应 `HomeWidget.data_widget`（`DataPlotWidget`）。连接后 `set_sensor_items()` 动态注册传感器，每个传感器生成一个 `QCheckBox` 和一个 `pg.PlotWidget`（基于 pyqtgraph）。`_display_data_timer` 以最高 15 Hz 频率触发 `update_display(data)`，只渲染当前时间窗口（默认 60 秒）内的数据点，避免长时间运行时画面卡顿。

---

## 命令窗口

![命令窗口截图](../images/home-command-widget.png)

命令窗口（`CommandWidget`）位于左侧控制区，用于手动输入和查看 G-code 交互记录。

---

### 响应显示区

**白话**：上方深色文字区域会实时显示平台返回的所有消息和你发送的指令，并按消息内容自动着色，方便区分类型。每条消息前有时间戳。

**技术说明**：`command_display`（`QPlainTextEdit`，只读）。`display_message(message)` 仅根据**消息文本的前缀**判断颜色，与"谁发的"无关：

| 颜色 | 触发条件 | 含义 |
|------|----------|------|
| 红色 `#f44336` | 以 `!!` 开头 | 错误消息 |
| 橙色 `#ff9800` | 含 `action:` | 系统动作 |
| 灰色 `#bdbdbd` | 以 `//` 开头 | 信息/提示消息 |
| 绿色 `#4caf50` | 以 `>` 开头 | 指令回显行 |
| 白色 `#ffffff` | 以上都不匹配 | 普通响应 |

!!! note "用户发送的指令显示为白色"
    点击"发送指令"时，`on_send_clicked` 把**原始 G-code**（如 `G1 E10 F300`）直接传给 `display_message`。由于原始 G-code 不以 `>` 开头，它落入"普通响应"分支，显示为**白色**而非绿色。绿色仅用于文本以 `>` 开头的行。

`KlipperWorker.gcode_response` 信号也连接到此槽，Klipper 的所有回复均会在此显示。

---

### G-code 输入框

**白话**：在下方输入框里输入任意 G-code 指令（如 `G1 E10 F300` 挤出 10 mm），按 Enter 或点击"发送指令"按钮即可发送。按上方向键可恢复上一条发送过的指令，方便重复操作。

**技术说明**：`command_input`（自定义 `CommandInput(QLineEdit)`）。按 Enter 或点击 `send_button` 均触发 `on_send_clicked`，通过 `command` 信号发给 `KlipperWorker.send_gcode`。上方向键触发 `upArrowPressed` 信号，`on_prev_clicked` 从 `command_cache` 列表弹出上一条指令填入输入框。未连接时输入框和发送按钮均禁用。

---

### 发送指令按钮

**白话**：点击此按钮将当前输入框中的 G-code 发送给平台，与按 Enter 效果相同。

**技术说明**：`send_button`（`QPushButton`，标签"发送指令"）。`clicked` 信号连接到 `on_send_clicked`。

---

## 挤出按钮（长按）

**白话**：按住此按钮，平台开始持续向前挤出丝材；松开立即停止。这是在没有 G-code 文件时手动控制进料的快捷方式。

**技术说明**：`extrude_button`（`QPushButton`，标签"挤出（长按）"）。`pressed` 信号触发 `on_extrude_pressed`：立即发出一段 G-code（`G91\nG1 E{step} F{feedrate}\n`）提升响应感，随后每隔 `jog_interval_ms`（默认 1000 ms）重复发送一次，直到 `released` 信号触发 `_extrude_timer.stop()`。每段的步长 `jog_step_mm = feedrate_mm_per_min / 60 × interval_s`（默认约 3.33 mm），使运动时间约等于发送间隔，避免 Klipper 运动队列堆积，松开后最多再走一小段即停止。挤出速度默认 200 mm/min。

---

## 回抽按钮（长按）

**白话**：按住此按钮，平台反向回抽丝材；松开立即停止。用于实验结束后清退余料，或出现丝材堵塞时快速后退。

**技术说明**：`retract_button`（`QPushButton`，标签"回抽（长按）"）。机制与挤出按钮完全对称，发送的 G-code 为 `G91\nG1 E-{step} F{feedrate}\n`（E 值取负）。`_retract_timer` 与 `_extrude_timer` 独立，两者共享相同的步长和间隔参数。

---

## 播放 / 暂停按钮（记录开关）

**白话**：点击此圆形按钮开始记录数据（按钮变为"暂停"图标），再次点击停止记录。每次开始会自动在桌面生成一个带时间戳的 CSV 文件；若相机在线，还会同步录制视频。

**技术说明**：`play_pause_button`（`QPushButton`，可切换，固定尺寸 80×80 px，圆形样式）。`toggled` 信号连接到 `MainWindow.on_toggle_play_pause(checked)`：

- **checked = True**（开始记录）：切换为暂停图标，生成 `~/Desktop/<时间戳>_autosave.csv` 并写入列标题；若相机在线同时启动 `VideoRecorder`。
- **checked = False**（停止记录）：切换回播放图标，关闭 CSV 文件（和视频文件）。

G-code 响应中的 `START_RECORDING` / `STOP_RECORDING` 动作标记也可自动触发此按钮状态切换。详见[数据记录](../concepts/data-recording.md)。

!!! note "按钮可能暂时消失"
    播放/暂停按钮和急停按钮放在同一个容器中，与下方的 **Klipper 状态控件**互斥显示。当 Klipper 处于非 `ready` 状态（`startup` / `shutdown` / `error`）时，状态控件弹出并隐藏这两个按钮；状态恢复 `ready` 后按钮重新出现（由 `sig_visible_changed` 信号驱动，见下文 Klipper 状态控件章节）。

---

## 急停按钮

**白话**：点击此按钮立即停止一切运动，同时清空当前记录会话的内存数据，相当于"紧急刹车"。仅在确认需要强制中止时使用。

**技术说明**：`stop_button`（`QPushButton`，使用 `emergency_stop.png` 图标，固定尺寸 80×80 px，透明背景）。`clicked` 信号连接到 `MainWindow.on_stop_clicked`，该槽依次调用 `init_data()`（清空内存数据队列）、将 `play_pause_button` 设为非选中状态（停止记录）、发出 `sigEmergencyStop` 信号，最终由 `KlipperWorker.emergency_stop` 通过 Moonraker 调用 `printer.emergency_stop`。

!!! warning "注意"
    急停后 Klipper 会进入 `shutdown` 状态，需在 Klipper 状态控件中点击"固件重启"或"Klipper 重启"方可恢复正常操作。

---

## Klipper 状态控件

![Klipper 状态控件截图](../images/home-klipper-status.png)

**白话**：正常运行时，此区域隐藏，不占界面空间。当 Klipper 出现异常（如 `startup` / `shutdown` / `error` 状态）时，它会自动弹出，显示当前状态、错误详情，以及"固件重启"和"Klipper 重启"两个修复按钮。状态恢复为 `ready` 后自动隐藏。

**技术说明**：`klipper_status_widget`（`KlipperStatusWidget`）。`KlipperWorker` 的 `sigKlipperState(state, message)` 信号驱动 `on_state_changed`：

- 状态圆点（`_dot`）颜色随状态变化：`ready`=绿色，`startup`=橙色，`shutdown`=灰色，`error`=红色。
- `state == "ready"` 时控件整体隐藏（`setVisible(False)`），并通过 `sig_visible_changed` 信号通知主页将播放/急停按钮容器重新显示。
- `_toggle_btn`（"▼ 详情"）展开/收起 `_detail_label` 中的错误信息。
- `_firmware_btn`（"固件重启"）触发 `KlipperWorker.restart_firmware`；`_klipper_btn`（"Klipper 重启"）触发 `KlipperWorker.printer_restart`。
