# 数据处理页

数据处理页（`DataProcessorWidget`）用于在测试结束后加载录制的 CSV 数据文件，自动清洗并分析挤出力随进线速度的关系，以散点图（含误差棒）呈现多温度下的流变曲线，并可将统计结果导出为新的 CSV 文件。

![数据处理页整体截图](../images/data-processor-page.png)

---

## 布局概览

页面分为左侧控制面板（最大宽度 400 px）和右侧绘图区两部分：
- **左侧**：依次排列"打开文件"按钮、"导出结果"按钮、裁剪滑块、日志区
- **右侧**：pyqtgraph 散点图，横轴为进线速度（mm/s），纵轴为挤出力（N），按温度分组着色并附误差棒

!!! note "关于"清洗数据"按钮"
    界面中存在一个 `clean_button`（`QPushButton`，标签"清洗数据"），但在当前版本中该按钮通过 `setVisible(False)` 隐藏（`data_processor_widget.py:47`）。打开 CSV 文件时，`open_csv_file()` 会在加载后自动调用 `clean_data()`，因此无需手动点击清洗按钮。

---

## 控件说明

### 打开文件按钮（`open_csv_button`）

**白话**：点击"打开文件（.csv）"按钮，弹出文件选择对话框，选择一个由 HEPiC 记录下来的 CSV 数据文件。选择后软件会自动完成以下操作：加载数据 → 清洗数据 → 绘图，全程无需再点其他按钮。日志区会显示加载结果（行数、列数）和清洗统计信息。

**技术说明**：`QPushButton`（`open_csv_button`，标签"打开文件（.csv）"）。点击触发 `open_csv_file()`（`data_processor_widget.py:71-91`）：用 `QFileDialog.getOpenFileName` 过滤 `*.csv`，通过 `pd.read_csv(file_path)` 读取为 DataFrame（`self.df`），并保存路径到 `self.csv_file_path`。加载成功后直接调用 `clean_data()` 触发清洗流程，失败则在日志区打印错误信息。

---

### 裁剪秒数滑块（`int_slider`）

**白话**：页面左侧有一个横向滑块，标签显示"裁剪秒数: X.X s"。拖动滑块可以从 0 到 20 秒之间调整裁剪时长（精度 0.1 s）。裁剪的含义是：在计算每个速度-温度组合的挤出力统计值时，去掉每步开头的若干秒数据，避免速度切换瞬间的过渡波动对均值和标准差产生干扰。每次拖动滑块后，图表会立刻用新的裁剪参数重新绘制。

**技术说明**：`QSlider`（`int_slider`，方向水平，范围 0–200，步长 1，初始值 0）。实际裁剪秒数 = 滑块值 × 0.1（`data_processor_widget.py:66`）。`valueChanged(int)` 信号连接到 `on_slider_value_changed(value)`（`data_processor_widget.py:65-69`）：更新 `self.clip_seconds`，刷新标签文字，清空图表后调用 `plot()` 重绘。`int_slider_label`（`QLabel`）实时显示当前裁剪秒数。

---

### 导出结果按钮（`export_button`）

**白话**：点击"导出结果"按钮，弹出文件保存对话框，将当前图表所展示的统计结果（每个温度-速度组合的挤出力均值和标准差）保存为新的 CSV 文件。默认文件名基于原始文件名加裁剪秒数自动生成（例：`run1_stats_clip2.0s.csv`）。若尚未完成清洗或图表无数据，按钮点击后日志区会提示无数据可导出。

**技术说明**：`QPushButton`（`export_button`，标签"导出结果"）。点击触发 `export_results()`（`data_processor_widget.py:155-180`）：检查 `self.stats_df` 是否为空，若有数据则构造默认文件名（`{stem}_stats_clip{clip}s.csv`），调用 `QFileDialog.getSaveFileName` 获取保存路径，用 `self.stats_df.to_csv(save_path, index=False)` 导出，结果（成功路径或错误信息）写入日志区。

---

### 日志区（`log_widget`）

**白话**：控制面板底部的日志文本区域，实时记录所有操作的反馈信息，例如文件加载是否成功、清洗出了多少步、导出到哪里等。如果出现错误，错误信息也会显示在这里。

**技术说明**：`LogWidget` 实例（`self.log_widget`）。整个 `DataProcessorWidget` 内部通过 `self.log_widget.update_log(message)` 在各操作节点写入消息，不对外暴露信号。

---

## 绘图区（`plot_widget`）

**白话**：右侧图表横轴为进线速度（mm/s），纵轴为挤出力（N）。每种温度用不同颜色的圆点表示，图例显示对应温度值（如 `200.0°C`）。每个圆点的上下误差棒表示该条件下多次测量的标准差，反映实验重复性。拖动裁剪滑块后，图表会自动刷新。

**技术说明**：`pg.PlotWidget`（`plot_widget`，横轴标签"进线速度 / mm/s"，纵轴标签"挤出力 / N"，启用图例）。`plot()`（`data_processor_widget.py:106-153`）按温度分组（`stats.groupby("temperature_C")`），为每组调用 `plot_widget.plot(...)` 绘制散点，再用 `pg.ErrorBarItem` 叠加误差棒；颜色通过 `pg.intColor(idx, hues=...)` 自动分配。

---

## 数据处理流程说明

打开 CSV 文件后，数据处理经过以下步骤（对应 `data_cleaning` 工具模块）：

1. **加载**：`pd.read_csv` 读取原始 CSV 文件（`open_csv_file()`，`data_processor_widget.py:84`）
2. **清洗**：`data_cleaning.clean_data(self.df)` 识别每个挤出速度步骤的边界，返回 `cleaned_steps`（步骤列表）、`data_clean`（清洗后的完整数据）和 `step_length`（推断的每步时长）（`clean_data()`，`data_processor_widget.py:100`）
3. **统计**：`data_cleaning.extrusion_statistics(self.cleaned_steps, clip=self.clip_seconds)` 计算每个温度-速度组合在裁剪后时间窗内的挤出力均值（`extrusion_force_N_mean`）和标准差（`extrusion_force_N_std`），结果存为 `self.stats_df`（`plot()`，`data_processor_widget.py:114`）
4. **绘图**：按温度分组，绘制均值散点 + 误差棒（`plot()`，`data_processor_widget.py:127-153`）
5. **导出**：将 `self.stats_df` 写入 CSV（`export_results()`，`data_processor_widget.py:177`）

!!! tip "何时需要调整裁剪秒数"
    若实验中每步速度切换后挤出力需要一段时间稳定，可增大裁剪秒数以跳过过渡期；裁剪过多会减少有效样本。建议先用裁剪 0 s 查看原始散点，再根据数据稳定所需时间调整。
