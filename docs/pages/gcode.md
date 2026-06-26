# G-code 页

G-code 页（`JobSequenceWidget`）是向 Klipper 发送打印任务的核心界面：在此加载或生成 G-code 文件、上传到 Klipper 并执行，执行过程中当前行高亮显示；页面右侧同步绘制速度/温度预览曲线。

![G-code 页整体截图](../images/gcode-page.png)

---

## 文本显示区

### G-code 文本显示区（`gcode_display`）

**白话**：页面中央的大文本框显示当前载入的 G-code 内容。默认为只读——可以浏览，但不能直接编辑。执行过程中，Klipper 当前正在处理的那一行会自动用蓝色背景高亮，方便跟踪进度。

**技术说明**：`QTextEdit`（`gcode_display`，`setReadOnly(True)`）。高亮由 `GcodeWidget.highlight_current_line(line_number)` 实现（`gcode_widget.py:137-155`）：将 `QTextCharFormat.FullWidthSelection` 背景色设为 `#456882`（蓝灰色），并通过 `setExtraSelections()` 渲染；每次有新的当前行时，旧高亮自动被替换（`extraSelections` 列表每次整体覆盖）。

---

## 工具栏控件

### 标题 `✏️` 编辑按钮（`edit_button`）

**白话**：文本框右上角有一个铅笔图标按钮（`✏️`）。默认状态下文本框只读。点击铅笔按钮后，按钮变为 `✅`，文本框变为可编辑状态，允许直接修改 G-code；再次点击恢复只读，按钮回到 `✏️`。

**技术说明**：`QPushButton`（`edit_button`，可切换，`setCheckable(True)`）。`toggled(bool)` 信号连接到 `on_toggle_edit(checked)`（`gcode_widget.py:81-83`），根据 `checked` 状态切换 `gcode_display.setReadOnly(not checked)`。

---

### 打开按钮（`open_button`）

**白话**：点击"打开"按钮，弹出文件选择对话框，仅接受 `.gcode` 扩展名的文件。选择文件后，G-code 内容立刻显示到文本框中，同时触发右侧速度/温度预览曲线刷新。

**技术说明**：`QPushButton`（`open_button`，标签"打开"）。点击触发 `on_click_open()`（`gcode_widget.py:85-100`）：`QFileDialog.getOpenFileName` 过滤 `*.gcode` 文件，读取文件内容后调用 `set_gcode(gcode)`。`set_gcode` 会发出 `sigGcode(str)` 信号，`JobSequenceWidget` 已将该信号连接到 `show_plots(gcode)`（`job_sequence_widget.py:49`），用于绘制预览曲线。

---

### 生成按钮（`gen_button`）

**白话**：点击"生成"按钮，弹出"生成动作序列"对话框（见下文"生成动作序列对话框"一节）。在对话框中填写速度范围、温度范围和每步时间后，软件会自动生成一段完整的挤出测试 G-code，覆盖所有温度-速度组合，并自动插入 `START_RECORDING` / `STOP_RECORDING` 等软件动作指令（详见"软件动作"一节）。生成结果直接填入文本框，可立即运行或手动修改。

**技术说明**：`QPushButton`（`gen_button`，标签"生成"）。点击触发 `on_click_gen()`（`gcode_widget.py:113-118`）：实例化 `JobSequenceDialog` 并以模态方式运行（`dialog.exec()`）；若用户点击 OK，调用 `dialog.get_job_sequence()` 获取生成的 G-code 字符串，再调用 `set_gcode(gcode)` 填入文本框。

---

### 运行按钮（`run_button`）

**白话**：点击"运行"按钮，软件将文本框中的当前 G-code 内容写入一个临时文件（`tmp.gcode`），然后上传到 Klipper 并立即切换到主页（标签页自动跳转到索引 0）开始监控执行进度。**注意：上传完成后应在主页点击"播放/记录"按钮才能启动数据采集；运行按钮本身不会开始记录数据。**

**技术说明**：`QPushButton`（`run_button`，标签"运行"）。点击触发 `on_click_run()`（`gcode_widget.py:103-111`）：从 `gcode_display.toPlainText()` 获取文本，创建 `GcodePositionMapper`（用于后续文件偏移→行号映射），将内容写入 `HEPiC/tab_widgets/tmp.gcode`，再通过 `sigFilePath(str)` 信号发出文件路径。`__main__.py` 有两条连接接收该信号：
- `sigFilePath → klipper_worker.upload_gcode_to_klipper`（`__main__.py:319`）——上传文件到 Klipper
- `sigFilePath → lambda _: self.tabs.setCurrentIndex(0)`（`__main__.py:217`）——自动跳转到主页

---

## 进度与当前行高亮

**白话**：G-code 在 Klipper 上执行时，Klipper 返回当前文件字节偏移（`file_position`）。软件通过 `GcodePositionMapper` 将字节偏移换算为行号，并将对应行高亮显示在文本框中，让你实时看到 Klipper 正在执行哪一行。

**技术说明**：`MainWindow` 定期收到 `sigFilePosition(int)` 信号，连接到 `GcodeWidget.update_file_position(file_position)`（`__main__.py:216`，`gcode_widget.py:181-193`）。`update_file_position` 使用 `GcodePositionMapper.get_line_number(file_position)` 换算后，若行号有效则：
1. 发出 `sigCurrentLine(int)` → `highlight_current_line(line_number)`：在文本框中高亮该行
2. 发出 `sigActiveGcode(str)` → `klipper_worker.set_active_gcode(gcode_line)`（`__main__.py:320`）：通知 Klipper Worker 当前活跃 G-code 指令

---

## 速度/温度预览曲线

**白话**：每次加载或生成 G-code 后，页面右侧会立刻出现两张折线图，分别显示整个任务序列中进线速度（mm/s）和热端温度（℃）随时间的变化预览。这些曲线是静态预测，并非实时测量值——仅供确认任务参数是否正确。

**技术说明**：`JobSequenceWidget` 中包含两个 `pg.PlotWidget`（`job_sequence_widget.py:27-32`），分别绘制 `filament_velocity_mms` 和 `hotend_temperature_C`。`GcodeWidget.sigGcode` 信号连接到 `JobSequenceWidget.show_plots(gcode)`（`job_sequence_widget.py:49`），该方法调用 `parse_gcode_time_series(gcode)` 解析 G-code 获取时间序列 `(t, ve, temp)`。进线速度与喷头温度是两条相互独立的曲线，分别通过各自的 `setData` 调用更新——`curves["filament_velocity_mms"].setData(t, ve)` 与 `curves["hotend_temperature_C"].setData(t, temp)`（`job_sequence_widget.py:56-57`）。

---

## 生成动作序列对话框

**白话**：点击"生成"按钮后出现的对话框，允许你用几个参数自动生成一套标准挤出流变测试序列（横扫速度 × 温度矩阵）。你只需填写速度范围（最小/最大/个数）、温度范围（最小/最大/个数）、每步时间，点击 OK，软件就会帮你写好完整的 G-code，包括加热等待、传感器归零、录制开始/结束等指令。

**技术说明**：`JobSequenceDialog`（`job_sequence_dialog.py`，继承 `QDialog`）。包含以下输入控件：

| 控件 | 类型 | 说明 |
|---|---|---|
| `vmin_input` | `QLineEdit` | 最小速度（mm/s） |
| `vmax_input` | `QLineEdit` | 最大速度（mm/s） |
| `vnum_input` | `QSpinBox`（0–100，默认 20） | 速度等分数量 |
| `tmin_input` | `QLineEdit` | 最小温度（℃） |
| `tmax_input` | `QLineEdit` | 最大温度（℃） |
| `tnum_input` | `QSpinBox`（0–100，默认 20） | 温度等分数量 |
| `tstep_input` | `QLineEdit` | 每步运行时间（s） |

`get_job_sequence()`（`job_sequence_dialog.py:57-106`）用 `numpy.linspace` 生成温度/速度点阵，按外温-内速循环构建 G-code 列表，并自动插入以下软件动作指令（第一个温度点时）：`ZERO_SENSORS`、`START_RECORDING`（首个温度-速度组合前）；最后追加 `STOP_RECORDING` 与 `FIRMWARE_RESTART`。

---

## 软件动作：G-code 响应触发的软件行为

**白话**：在 G-code 中写一行特殊的注释指令（格式：`M118 <动作关键字>`），Klipper 执行到该行时会通过 `gcode_response` 消息回传给软件，软件识别出关键字后自动执行对应的操作——例如自动开始/停止数据录制、归零传感器、更新质检状态栏等，完全无需手动点击界面按钮。这样你可以把整个测试流程（加热→归零→录制→扫速→停止）完全编入 G-code 文件，实现自动化测试。

**技术说明**：`MainWindow.handle_gcode_response(response)`（`__main__.py:342-363`）接收 `klipper_worker.gcode_response` 信号，调用 `_extract_software_action(response)` 识别动作（`__main__.py:365-377`）。识别逻辑：先剥去行首的 `//`、`echo:`、`action:` 前缀，再取第一个空格前的词（大写化）与支持集合对比。

**支持的软件动作集合**（源码 `__main__.py:376`）：

| 动作关键字 | 触发效果 |
|---|---|
| `START_RECORDING` | 勾选主页"播放/记录"按钮（等同于手动开始数据采集） |
| `STOP_RECORDING` | 取消勾选主页"播放/记录"按钮（停止数据采集） |
| `START_QUALITY_CHECK` | 在质检模式已激活的前提下，触发挤出进度推进 |
| `STOP_QUALITY_CHECK` | 在质检模式已激活的前提下，停止质检流程 |
| `STATUS` | 将 `STATUS` 后面的文字显示在质检状态栏和主页状态文本中（例：`M118 STATUS 正在加热` → 状态栏显示"正在加热"） |
| `ZERO_SENSORS` | 对所有可归零传感器（通过 `worker.get_zeroable_sensor_names()` 枚举）执行 `worker.zero_sensor()` |

!!! note "关于 `START_QUALITY_CHECK` / `STOP_QUALITY_CHECK`"
    这两个动作仅在质检模式（`quality_check_widget`）处于激活状态（`is_checking == True`）时才有实际效果；若质检模式未开启，调用会静默返回。

!!! tip "在 G-code 中嵌入软件动作的写法"
    使用 Klipper 的 `M118` 指令发送消息，格式如下：
    ```gcode
    M118 START_RECORDING
    M118 STATUS 正在加热至 200℃
    M118 ZERO_SENSORS
    M118 STOP_RECORDING
    ```
    Klipper 接收到 `M118` 后会将消息体回传给主机，`handle_gcode_response` 检测到关键字即执行对应软件操作。
