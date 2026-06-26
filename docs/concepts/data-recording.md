# 数据记录

本页说明 HEPiC 的数据采集机制：数据怎样被采集、存储哪些列、如何开始/停止记录，以及文件保存到哪里。

---

## 采集线程与 UI 刷新的解耦

**白话：** 传感器数据的采集和界面的刷新是两件独立的事，互不干扰。即使界面繁忙，数据也不会丢失；即使数据采集很快，界面也不会被拖慢。

**技术说明：** 应用启动连接后，后台会同时运行两个独立的计时机制：

| 机制 | 频率（默认） | 职责 |
|------|------------|------|
| `_DataCollectorThread`（独立线程） | `data_frequency`（默认 **10 Hz**） | 调用 `grab_status()` 快照当前所有传感器与 Klipper 状态，追加到内存队列；如已开启记录，同时写一行到 CSV |
| `_display_data_timer`（Qt 定时器） | `min(data_frequency, 15)`（最高 **15 Hz**） | 把内存队列中的数据推送给图表控件刷新显示 |

`data_frequency` 和显示上限均通过 `config.json` 配置。`_DataCollectorThread` 使用 `time.perf_counter()` 精确计时，若某次采集耗时超出间隔，直接重置而非堆积补偿。

---

## 采集的数据列

每个采集周期，`grab_status()` 会汇集以下信息组成一行记录：

### 固定列（始终存在）

| 列名 | 来源 | 说明 |
|------|------|------|
| `time_s` | 本地时钟 | 自本次会话开始的经过时间（秒） |
| `temperature_C` | Moonraker / Klipper | 目标热端温度（`extruder.target`） |
| `feedrate_mms` | Moonraker / Klipper | 当前实时挤出速度 mm/s（`motion_report.live_extruder_velocity`） |
| `measured_temperature_C` | Moonraker / Klipper | 实测热端温度（`extruder.temperature`） |
| `measured_feedrate_mms` | TCP 传感器（计米编码器） | 由旋转编码器计算的丝材实测速度 mm/s |

### 动态传感器列（按硬件可用性注册）

| 列名 | 来源 | 说明 |
|------|------|------|
| `die_diameter_px` | Hikrobot 工业相机 + 图像处理 | 口模处熔体直径（像素值），由视觉模块检测 |
| `die_temperature_C` | Optris 红外热像仪 | 口模处熔体出口温度（°C），由红外 ROI 均值计算 |
| *其他传感器列* | TCP 数据服务器 | 由 hepic_server 的 `sensor_config` 动态决定（如 `extrusion_force_N`、`meter_count_mm` 等） |

!!! note "传感器列动态配置"
    TCP 连接建立后，hepic_server 会推送一条 `sensor_config` 消息，列出当前平台配置的所有传感器名称。HEPiC 据此动态注册对应的数据列，因此实际 CSV 的列数取决于平台配置。

---

## 开始与停止记录

**白话：** 主页上有一个播放/暂停按钮，按下即开始记录，再按一次停止。每次开始都会自动创建一个新文件，不会覆盖上次的数据。

**技术说明：** 主页的播放/暂停按钮（`play_pause_button`，可切换状态）触发 `on_toggle_play_pause(checked)` 槽函数：

- **按下（开始记录）：** 以当前时间生成文件名前缀（格式 `YYYYmmdd_HHMMSS`），在桌面创建 CSV 文件并写入列标题行，随后将 `is_recording` 置为 `True`。此后每个采集周期的数据会立即追加写入。
- **再次按下（停止记录）：** 将 `is_recording` 置为 `False`，刷新并关闭 CSV 文件。

!!! note "G-code 触发记录"
    G-code 响应中若含 `START_RECORDING` / `STOP_RECORDING` 动作标记，软件会自动模拟按下/松开播放按钮，实现从平台端控制记录时机。

---

## 文件保存位置

### CSV 数据文件

每次开始记录，CSV 文件自动保存到：

```
~/Desktop/<时间戳>_autosave.csv
```

示例：`C:\Users\<用户名>\Desktop\20241015_143022_autosave.csv`

文件采用 UTF-8 编码，逗号分隔，首行为列名，后续每行对应一个采集周期的数据快照。

### 视频文件（可选）

若 Hikrobot 相机初始化成功，记录期间会**同步录制**图像处理后的视频：

```
~/Desktop/<时间戳>_video.mkv
```

视频由 `VideoRecorder` 模块使用 FFmpeg 编码为 MKV 格式，帧率与相机帧率一致。停止记录时视频文件同步关闭。

!!! warning "注意"
    若相机未连接或初始化失败，`record_timelapse` 功能将不可用，此时只有 CSV 文件生成。

---

## 相关页面

- 播放/暂停按钮的位置与操作 → [界面说明 / 主页](../pages/home.md)
- 软件架构与两条连接 → [核心概念 / 软件架构](./architecture.md)
