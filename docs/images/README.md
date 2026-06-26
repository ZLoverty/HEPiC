# 待补截图清单

> **说明**：本目录下所有 `.png` 文件当前均为 **1×1 像素占位文件**，需在软件稳定后替换为真实截图。
>
> MkDocs 严格构建（`--strict`）要求每个被引用的文件在构建时必须存在，因此**请勿删除**这些占位文件，应原地替换（覆盖同名文件）。
>
> 共 **20 个**占位文件（19 张截图 + 1 张架构图）。

---

## 架构示意图（非截图）

| 文件名 | 引用页面 | 说明 |
|--------|----------|------|
| `architecture-overview.png` | `docs/index.md`、`docs/concepts/architecture.md` | HEPiC 软件架构总览图（由设计人员绘制，不是界面截图）。应展示 HEPiC 客户端、TCP 数据通道、Moonraker WebSocket、Klipper 之间的连接关系。 |

---

## 界面截图

### 连接页（`pages/connection.md`）

| 文件名 | 说明 |
|--------|------|
| `connection-page.png` | 连接页整体截图，展示 IP 地址输入框、端口设置、「连接」按钮以及自检状态列表（5 步自检的逐行通过/失败状态）。 |

### 主页（`pages/home.md`）

| 文件名 | 说明 |
|--------|------|
| `home-page.png` | 主页整体截图，展示全部控件区域的布局（状态面板、数据曲线、ROI 预览、命令窗口等）。 |
| `home-klipper-status.png` | Klipper 状态控件截图，展示打印机状态文字（如「就绪」/「打印中」）及颜色指示。 |
| `home-status-panel.png` | 状态面板截图，展示温度、转速等实时数值读数区域。 |
| `home-data-plot.png` | 实时数据曲线图截图，展示力值/温度等实时折线曲线以及录制中的动态效果。 |
| `home-dieswell-roi.png` | 模口膨胀 ROI 视图截图，展示从摄像头画面中裁剪出的模口区域图像。 |
| `home-ir-roi.png` | 红外 ROI 视图截图，展示热成像摄像头输出的红外区域图像。 |
| `home-command-widget.png` | 命令窗口截图，展示 G-code 命令输入框与响应输出区域。 |

> **注意**：`home-control-buttons.png` 已存在于目录中，但**当前没有任何文档页面引用该文件**（孤立占位，见下方「孤立文件」章节）。

### 视觉页（`pages/vision.md`）

| 文件名 | 说明 |
|--------|------|
| `vision-page.png` | 视觉页整体截图，展示摄像头画面预览、曝光/增益参数滑块及 ROI 设置控件。 |

### 红外页（`pages/ir.md`）

| 文件名 | 说明 |
|--------|------|
| `ir-page.png` | 红外页整体截图，展示热成像摄像头画面预览及红外参数设置区域。 |

### G-code 页（`pages/gcode.md`）

| 文件名 | 说明 |
|--------|------|
| `gcode-page.png` | G-code 页整体截图，展示命令输入区、历史记录列表以及软件动作（软件动作触发器列表）。 |

### 数据处理页（`pages/data-processor.md`）

| 文件名 | 说明 |
|--------|------|
| `data-processor-page.png` | 数据处理页整体截图，展示文件选择区、数据曲线浏览器、参数配置面板以及导出功能区。 |

### 质检模式（`pages/quality-check.md`）

| 文件名 | 说明 |
|--------|------|
| `quality-check-page.png` | 质检模式整体截图，展示完整质检界面布局（材料信息、力值曲线、操作面板、系统信息、历史记录）。 |
| `quality-check-material-panel.png` | 材料信息面板截图，展示材料名称、批次、操作员等填写字段。 |
| `quality-check-force-plot.png` | 力值曲线图截图，展示质检过程中实时采集的力值折线曲线及阈值线。 |
| `quality-check-action-panel.png` | 质检操作面板截图，展示「开始质检」「停止」等按钮及质检进度状态提示。 |
| `quality-check-system-panel.png` | 系统信息面板截图，展示与 Klipper 同步的打印机实时状态数值（温度、转速等）。 |
| `quality-check-history.png` | 质检历史截图，展示历史质检记录列表（批次、时间、结论等字段）。 |

---

## 孤立文件（当前未被任何页面引用）

| 文件名 | 状态 | 建议 |
|--------|------|------|
| `home-control-buttons.png` | **孤立占位**，无页面引用 | 若主页文档中有「控制按钮」截图需求，请在 `pages/home.md` 中添加对应的 `![控制按钮截图](../images/home-control-buttons.png)` 引用；若该截图已合并到 `home-page.png` 中，则可在替换占位时将其删除（先移除引用再删文件，或直接忽略）。 |

---

## 替换步骤

1. 运行软件并导航到对应页面。
2. 截图并裁剪至合适尺寸（建议宽度 1200–1600 px，PNG 格式）。
3. 以**相同文件名**覆盖 `docs/images/` 下对应占位文件。
4. 运行 `.venv/Scripts/python -m mkdocs build --strict` 确认构建仍然通过。
5. 提交更改：`git add docs/images/ && git commit -m "docs: add real screenshots"`。
