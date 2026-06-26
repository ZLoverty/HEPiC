# 质检模式

质检模式页（`QualityCheckWidget`）用于对指定材料执行一次完整的挤出质量检查：根据材料档案自动生成并下发 G-code、实时显示挤出力数据和稳定性评估，并将结果记录在历史列表中。

![质检模式整体截图](../images/quality-check-page.png)

---

## 材料信息面板

![材料信息面板截图](../images/quality-check-material-panel.png)

材料信息面板（`材料信息`）显示当前选中材料的档案参数，这些参数同时用于生成质检 G-code 和评估挤出力是否合格。

---

### Family 下拉框（`material_family_combo`）

**白话**：选择材料的大类（Family），例如 PLA、ABS 等。切换后，下方的 PI Code 下拉框会自动更新为该 Family 下的所有材料编号，材料属性区域也会同步刷新。

**技术说明**：`QComboBox`（`material_family_combo`）。初始值来自启动时的默认材料表（`DEFAULT_MATERIAL_FAMILIES`，`materials.py:3-16`）；`QualityCheckWidget` 第一次显示时会从 YAML 数据库（`MaterialDatabase`，`material_database.py`）异步加载真实数据并替换。`currentTextChanged` 信号连接到 `on_material_family_changed(family)`（`quality_check_widget.py:407-409`），后者调用 `_populate_pi_code_combo_box(family)` 刷新 PI Code 列表，再调用 `update_material_properties_display()` 更新属性显示和曲线区间带。

---

### PI Code 下拉框（`material_combo`）

**白话**：在选定的 Family 下，选择具体的材料编号（PI Code）。切换后，下方的温度、速度、力范围等参数立刻更新。

**技术说明**：`QComboBox`（`material_combo`）。`currentTextChanged` 信号连接到 `update_material_properties_display()`（`quality_check_widget.py:231`），该方法从内存中的 `material_families` 字典读取对应属性，并同步更新曲线图的合格/优秀区间带（`qualified_band`、`excellent_band` 及四条虚线分界线，`quality_check_widget.py:439-456`）。

---

### 材料属性显示（温度 / 速度 / 优秀范围 / 合格范围 / 稳定阈值）

**白话**：面板中间区域用五行只读数字展示当前 PI Code 的档案参数。这些数值由材料数据库决定，不可在此处编辑。

| 字段 | 说明 | 单位 |
|---|---|---|
| 温度 | 质检目标挤出温度 | °C |
| 速度 | 质检挤出速度 | mm/s |
| 优秀范围 | 挤出力优秀区间（下限 – 上限） | N |
| 合格范围 | 挤出力合格区间（下限 – 上限） | N |
| 稳定阈值 | 力值标准差的稳定/警告分界（见下文） | N |

**技术说明**：五个 `QLabel`（`temperature_value`、`speed_value`、`excellent_force_range_value`、`force_range_value`、`stability_threshold_value`，`quality_check_widget.py:235-248`）均由 `update_material_properties_display()` 从 `material_families[family][pi_code]` 字典读取并填写，键名分别为 `temperature`、`speed`、`excellent_force_range`（tuple）、`force_range`（tuple）、`stability_threshold`。材料属性的默认后备来自 `DEFAULT_MATERIAL_FAMILIES`（PLA / L1002：温度 200 °C，速度 30 mm/s，优秀范围 4.5–5.5 N，合格范围 3.0–7.0 N，稳定阈值 0.1 N）；生产数据由 YAML 文件覆盖。

---

## 系统信息面板

![系统信息面板截图](../images/quality-check-system-panel.png)

系统信息面板（`系统信息`）实时显示来自 Klipper 的平台状态和传感器读数。

---

### 实时温度（`system_temperature_value`）

**白话**：显示热端当前实测温度。质检未开始或 Klipper 断线时显示 `--`。

**技术说明**：`QLabel`（`system_temperature_value`）。由 `update_klipper_status(data)` 槽更新（`quality_check_widget.py:547-553`），读取 `data["measured_temperature_C"]`；若为 `NaN` 则显示 `--`，否则格式化为一位小数。该槽由 `__main__.py:211` 中的 `sigNewStatus.connect` 连接，每次 Klipper 状态刷新时触发。

---

### 实时挤出速度（`system_feedrate_value`）

**白话**：显示 Klipper 当前上报的挤出速度设定值，单位 mm/s。质检 G-code 发出后若此值与材料档案中的速度匹配，说明 Klipper 已按预设速度运行。

**技术说明**：`QLabel`（`system_feedrate_value`）。由 `update_klipper_status(data)` 读取 `data["feedrate_mms"]`；若为 `NaN` 则显示 `--`，否则格式化为一位小数（`quality_check_widget.py:547-553`）。

---

### 实时挤出力（`system_force_value`，英雄数字）

**白话**：页面上最显眼的大字数字，格式为 `均值 ± 标准差`（单位 N），实时反映当前挤出力的平均水平和波动幅度。数据不足 10 个采样点时显示 `--`。

**技术说明**：`QLabel`（`system_force_value`，28pt 粗体，`quality_check_widget.py:297-300`）。值由 `update_stability_indicator()` 计算并填写（`quality_check_widget.py:559-573`）：调用 `evaluate_force_window(extrusion_force_cache, material_properties)`（`evaluator.py:41-72`），取滑动窗口最近 200 个采样点的总体标准差（`pstdev`）和算术平均（`fmean`）；少于 10 个点时返回 `None`，显示 `--`。

---

### 状态消息（`status_message_label`）

**白话**：蓝色斜体的单行文字，显示质检流程的当前阶段说明，例如"正在加热"、"正在挤出"、"质检完毕，请记录数据"。内容由 G-code 中的 `M118 STATUS <文字>` 指令驱动，无需手动干预。

**技术说明**：`QLabel`（`status_message_label`，颜色 `#2980b9`，斜体，`quality_check_widget.py:308-311`）。由 `set_status_message(msg)` 槽更新；`__main__.py:391-401` 中的 `_set_quality_check_status_message` 解析 Klipper 返回的 `STATUS` 软件动作后调用该槽。详见 [G-code 页 → 软件动作](gcode.md)。

---

### 挤出进度条（`extrusion_progress_bar`）

**白话**：质检挤出过程中，进度条从 0% 推进到 100%，反映挤出动作的预计完成度。进度基于时间估算，不是实际丝材位移——质检停止后进度条自动归零。

**技术说明**：`QProgressBar`（`extrusion_progress_bar`，范围 0–100，`quality_check_widget.py:312-317`）。进度推进由 `_progress_timer`（间隔 100 ms）驱动，`_tick_extrusion_progress()` 每次累加 100 ms 后按 `elapsed / duration * 100` 计算百分比（`quality_check_widget.py:512-518`）。预计总时长 `_extrusion_duration_s` 由 `start_extrusion_progress()` 计算：优先读取材料属性中的 `quality_check_extrude_length_mm`，否则退化为 `speed * 60.0`（mm），再除以 `speed`（mm/s）得到秒数（`quality_check_widget.py:501-510`）。进度条由 `START_QUALITY_CHECK` 软件动作触发启动（`__main__.py:404-408`）；点击"停止质检"后 `_progress_timer` 停止，值归零（`quality_check_widget.py:490-491`）。

---

## 质检操作面板

![质检操作面板截图](../images/quality-check-action-panel.png)

质检操作面板（`质检操作`）包含开始/停止按钮和两个状态指示灯。

---

### 开始质检 / 停止质检按钮（`check_button`）

**白话**：点击"开始质检"，软件立刻按当前 PI Code 的材料档案生成一段完整的质检 G-code，发送给 Klipper 执行——Klipper 会先加热到目标温度，归零传感器，然后以指定速度挤出指定长度的丝材。此时按钮变为红色的"停止质检"；再次点击可随时中断，并将本次结果写入质检历史。

**技术说明**：`QPushButton`（`check_button`，最小高度 56 px，`quality_check_widget.py:322-327`）。点击触发 `on_quality_check_clicked()`（`quality_check_widget.py:458-496`）。

- **启动流程**（`is_checking == False` → `True`）：
  1. 清空力值缓存和历史评估。
  2. 两个指示灯重置为"未知"（灰色）。
  3. 调用 `build_quality_check_gcode(material_properties)`（`gcode.py:4-35`）生成 G-code，通过 `quality_check_gcode_requested` 信号传递给 `__main__.py`，后者经 `on_quality_check_gcode_requested` 异步调用 `klipper_worker.send_gcode(gcode)`（`__main__.py:333-339`）。
  4. 以 100 ms 间隔启动 `data_timer`（驱动 `on_data_update_timeout`，当前该槽为空函数）。

- **停止流程**（`is_checking == True` → `False`）：
  1. 停止 `data_timer` 和 `_progress_timer`，进度条归零。
  2. 两个指示灯重置为"未知"。
  3. 调用 `_record_quality_check_result()` 将本次均值/标准差写入历史。

生成的 G-code 序列（`gcode.py:13-34`）：

```gcode
M118 STATUS 正在加热
M109 S<temperature>        ; 等待加热完成
M118 STATUS 正在归零传感器
G91
G1 E-10 F600               ; 退料 10 mm
M400
G4 P2000
M118 ZERO_SENSORS          ; 触发传感器归零软件动作
G4 P500
G1 E10 F100                ; 预压 10 mm（低速）
M400
M118 START_QUALITY_CHECK   ; 触发进度条启动
M118 STATUS 正在挤出
M83
G1 E<length> F<feedrate>   ; 正式挤出
M400
M118 STOP_QUALITY_CHECK    ; 触发停止质检软件动作
M118 STATUS 质检完毕，请记录数据
FIRMWARE_RESTART
```

!!! warning "注意"
    `FIRMWARE_RESTART` 位于 G-code 末尾，Klipper 执行到此处会重启固件。`STOP_QUALITY_CHECK` 软件动作触发后，`__main__.py` 会调用 `on_quality_check_clicked()` 自动停止质检（`__main__.py:410-414`），效果与手动点击"停止质检"相同。

---

### 力值指示灯（`force_expectation_indicator`）

**白话**：圆形指示灯，显示当前挤出力均值是否落在材料档案规定的范围内。绿色表示均值在优秀范围内；黄色表示在合格范围内但不够优秀；红色表示超出合格范围；灰色表示数据不足（少于 10 个采样点）或质检未激活。

| 颜色 | 状态值 | 含义 |
|---|---|---|
| 灰色 `#888888` | `unknown` | 数据不足或未质检 |
| 绿色 `#27ae60` | `stable` | 均值在优秀范围内（`excellent_min ≤ mean ≤ excellent_max`） |
| 黄色 `#f39c12` | `warning` | 均值在合格范围内但在优秀范围外（`force_min ≤ mean ≤ force_max`） |
| 红色 `#e74c3c` | `unstable` | 均值超出合格范围 |

**技术说明**：`StatusIndicator`（64×64 px，`quality_check_widget.py:41-68`）。颜色由 `update_status(status)` 设置（CSS `border-radius: 32px` 实现圆形外观）。`force_status` 字段来自 `ForceEvaluation`（`evaluator.py:60-65`）：`mean` 在 `excellent_force_range` 内为 `"stable"`，在 `force_range` 内为 `"warning"`，否则为 `"unstable"`。

---

### 稳定性指示灯（`status_indicator`）

**白话**：宽条形指示灯，显示当前力值的波动是否稳定。绿色表示波动很小（优秀）；黄色表示轻微波动（可接受）；红色表示波动过大；灰色表示数据不足或未质检。

| 颜色 | 状态值 | 稳定性标准 |
|---|---|---|
| 灰色 `#888888` | `unknown` | 数据不足或未质检 |
| 绿色 `#27ae60` | `stable` | 标准差 < 稳定阈值（`std < threshold`） |
| 黄色 `#f39c12` | `warning` | 标准差在一倍到两倍阈值之间（`threshold ≤ std < 2×threshold`） |
| 红色 `#e74c3c` | `unstable` | 标准差 ≥ 两倍阈值（`std ≥ 2×threshold`） |

**技术说明**：`StabilityBarIndicator`（80×52 px，`quality_check_widget.py:71-99`）。`stability_status` 字段来自 `ForceEvaluation`（`evaluator.py:52-58`）。默认阈值 `DEFAULT_STABILITY_THRESHOLD = 0.1 N`（`evaluator.py:9`）；材料档案中可通过 `stability_threshold` 字段覆盖此默认值。两个阈值边界：第一档（稳定→警告）为 `threshold`，第二档（警告→不稳定）为 `2 × threshold`。

---

## 实时挤出力曲线图（`plot_widget`）

![力值曲线图截图](../images/quality-check-force-plot.png)

**白话**：页面下半部分是实时挤出力折线图，横轴为时间（s），纵轴为挤出力（N）。图上叠加了两个彩色区间带，帮助直观判断力值是否合格。质检期间数据滚动更新；质检停止后曲线保留，方便截图存档。

**区间带说明**：

| 区间带 | 颜色 | 含义 |
|---|---|---|
| 优秀区间带（`excellent_band`） | 绿色半透明（`#27ae60`，透明度约 18%） | 挤出力的优秀范围 |
| 合格区间带（`qualified_band`） | 黄色半透明（`#f1c40f`，透明度约 14%） | 挤出力的合格范围 |
| 优秀上/下界线（`excellent_upper` / `excellent_lower`） | 绿色虚线 | 优秀范围的精确边界 |
| 合格上/下界线（`qualified_upper` / `qualified_lower`） | 黄色虚线 | 合格范围的精确边界 |

**技术说明**：`pg.PlotWidget`（`quality_check_widget.py:350-401`）。实时力值曲线 `force_curve`（蓝色，`#2980b9`，宽度 2）由 `update_plot()` 刷新（`quality_check_widget.py:555-557`）。区间带使用两个 `pg.LinearRegionItem`（水平方向，不可拖动）和四条 `pg.InfiniteLine`（水平，虚线）实现，区间值在每次切换材料时由 `update_material_properties_display()` 同步更新。数据缓存为 `deque(maxlen=300)`，存储最近 300 个采样点；评估窗口取最近 200 个点（`evaluator.py:46`）。

---

## 质检历史（`history_text`）

![质检历史截图](../images/quality-check-history.png)

**白话**：页面左侧面板是质检历史记录，每次点击"停止质检"后自动追加一条记录，最新的在最上方。每条记录包含时间戳和本次质检的均值 ± 标准差结果（及对应的 PI Code）。若数据不足（少于 10 个采样点），记录为"数据不足（PI Code）"。

**技术说明**：`QTextEdit`（`history_text`，只读，最大宽度 350 px，`quality_check_widget.py:167-173`）。历史列表 `_quality_check_history` 为 `list[tuple[str, str]]`，新记录插入到索引 0（最前）。`_render_history()` 使用 `QTextCharFormat` 将时间戳染成灰色（`#999999`），正文保持默认颜色（`quality_check_widget.py:189-200`）。时间戳格式为 `HH:MM`（`datetime.now().strftime("%H:%M")`）。

---

## 典型工作流程

1. 在 **Family** 和 **PI Code** 下拉框中选择待检材料。
2. 核认材料信息面板中的温度、速度、力范围参数是否与实物批次一致。
3. 确保 Klipper 已连接（见[连接页](connection.md)）。
4. 点击**开始质检**——软件自动生成并下发 G-code，Klipper 开始加热。
5. 等待**状态消息**依次显示"正在加热"→"正在归零传感器"→"正在挤出"。
6. 挤出过程中观察：
   - **实时挤出力**英雄数字及曲线是否落在目标区间带内。
   - **力值指示灯**是否为绿色（优秀）或黄色（合格）。
   - **稳定性指示灯**是否为绿色（稳定）。
7. Klipper 挤出完成后自动触发 `STOP_QUALITY_CHECK`，质检停止，结果写入历史。
8. 在**质检历史**中查看本次均值 ± 标准差，判断该批次材料是否合格。
