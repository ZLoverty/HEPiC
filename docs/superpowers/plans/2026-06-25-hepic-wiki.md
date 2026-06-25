# HEPiC 用户 Wiki Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个面向用户的 HEPiC 中文 wiki(MkDocs + Material,部署到 GitHub Pages),从 GUI 使用者视角逐控件用「白话 + 技术说明」两层语言讲解。

**Architecture:** 在仓库 `docs/` 下编写 MkDocs 文档站,`mkdocs.yml` 配置导航与主题,GitHub Actions 自动构建并发布到 GitHub Pages。文档按 GUI 标签页组织,每页编写前先重新核对对应的 widget 源码,确保描述准确。

**Tech Stack:** MkDocs, mkdocs-material 主题, GitHub Actions, Python(已有 .venv)。

## Global Constraints

- 语言:中文为主。技术名词(G-code、ROI、TCP、Klipper、Moonraker、PI Code 等)保留原文。
- 每个控件统一模板:`**白话**:…` + `**技术说明**:…`(技术说明仅在必要时,点到为止,不深入实现)。
- 截图一律预留占位:`![说明](../images/<name>.png)`,实际图片不生成。
- 文档内部链接用相对路径;`mkdocs build --strict` 必须零警告通过(断链/孤儿页会报错)。
- 所有事实以源码为准,不臆测控件行为。
- MkDocs 文档源放在 `docs/` 根下的功能子目录;`docs/superpowers/` 已存在(spec/plan),不要纳入 wiki 导航。

## 验证说明(适用于每个任务)

文档项目没有单元测试,验证方式统一为:

- `mkdocs build --strict 2>&1` → 退出码 0、无 WARNING/ERROR。
- 人工内容核对:打开新写的页面,确认每个声称的控件在对应源码里确实存在。

每个任务最后一步是 `mkdocs build --strict` 通过后提交。

---

### Task 1: MkDocs 骨架与部署

**Files:**
- Create: `mkdocs.yml`
- Create: `docs/index.md`
- Create: `docs/images/.gitkeep`
- Create: `.github/workflows/docs.yml`
- Modify: `requirements-docs.txt`(新建,记录文档依赖)

**Interfaces:**
- Produces: 可用的 `mkdocs build` 环境;导航树骨架(后续任务往里填页面);`docs/index.md` 首页。

- [ ] **Step 1: 安装文档依赖并记录**

```bash
cd "c:/Users/zhengyang/Documents/GitHub/HEPiC"
.venv/Scripts/python -m pip install mkdocs mkdocs-material
```

创建 `requirements-docs.txt`:

```
mkdocs>=1.6
mkdocs-material>=9.5
```

- [ ] **Step 2: 写 `mkdocs.yml`**

```yaml
site_name: HEPiC 使用手册
site_description: Hotend Extrusion Platform 控制软件 — 用户 wiki
docs_dir: docs
theme:
  name: material
  language: zh
  features:
    - navigation.sections
    - navigation.top
    - search.suggest
    - content.code.copy
  palette:
    - scheme: default
      toggle:
        icon: material/weather-night
        name: 切换到深色模式
    - scheme: slate
      toggle:
        icon: material/weather-sunny
        name: 切换到浅色模式
markdown_extensions:
  - admonition
  - attr_list
  - md_in_html
  - toc:
      permalink: true
  - pymdownx.highlight
  - pymdownx.superfences
nav:
  - 首页: index.md
  - 快速开始: getting-started.md
  - 核心概念:
      - 软件架构: concepts/architecture.md
      - 数据记录: concepts/data-recording.md
  - 界面说明:
      - 连接页: pages/connection.md
      - 主页: pages/home.md
      - 视觉页: pages/vision.md
      - 红外页: pages/ir.md
      - G-code 页: pages/gcode.md
      - 数据处理页: pages/data-processor.md
      - 质检模式: pages/quality-check.md
not_in_nav: |
  superpowers/**
```

- [ ] **Step 3: 写 `docs/index.md`(首页/总览)**

内容要点:
- HEPiC 是什么(从 `README.md`:Hotend Extrusion Platform (基于树莓派) 控制软件,用于 FDM 过程中相关量的同步测量)。
- 一句话讲它能做什么:连接树莓派平台、实时监控温度/挤出力/视觉/红外、跑 G-code、记录数据、做材料质检。
- 架构总览图占位:`![架构总览](images/architecture-overview.png)`。
- 给读者的导航:指向「快速开始」和「界面说明」。

- [ ] **Step 4: 写 `.github/workflows/docs.yml`(自动部署到 GitHub Pages)**

```yaml
name: Deploy docs
on:
  push:
    branches: [master, dev]
    paths:
      - "docs/**"
      - "mkdocs.yml"
      - "requirements-docs.txt"
      - ".github/workflows/docs.yml"
permissions:
  contents: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-docs.txt
      - run: mkdocs gh-deploy --force
```

- [ ] **Step 5: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict`
Expected: 退出码 0,无 WARNING/ERROR(此时导航里引用了尚未创建的页面会报错,所以本任务需为每个 nav 条目建占位文件——见 Step 6)。

- [ ] **Step 6: 为后续页面建占位文件**

为 nav 中尚不存在的页面各建一个最小占位(`# 标题` + 一行「内容编写中」),让 `--strict` 通过:
`docs/getting-started.md`、`docs/concepts/architecture.md`、`docs/concepts/data-recording.md`、`docs/pages/{connection,home,vision,ir,gcode,data-processor,quality-check}.md`。

再次 Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add mkdocs.yml requirements-docs.txt docs/ .github/workflows/docs.yml
git commit -m "docs: scaffold MkDocs wiki site and CI deploy"
```

---

### Task 2: 快速开始页

**Files:**
- Modify: `docs/getting-started.md`(替换占位)
- 参考源:`README.md`、`HEPiC/__main__.py`(`start_app` 的 `-t/--test` 参数)、`pyproject.toml`(入口 `hepic`)

**Interfaces:**
- Consumes: Task 1 的站点骨架。
- Produces: 完整的安装/启动页。

- [ ] **Step 1: 核对来源**

Read `README.md`、`HEPiC/__main__.py`(确认 `-t` 测试模式)、`pyproject.toml`(确认 `hepic` 命令入口)。

- [ ] **Step 2: 写 `docs/getting-started.md`**

覆盖:
- 依赖安装:Hikrobot SDK、Optris SDK、FFmpeg(`winget install ffmpeg`)。
- 克隆仓库、建 venv、`pip install .`、运行 `hepic`。
- 测试模式:`hepic -t`(白话:不接硬件也能打开界面演示;技术说明:`-t/--test` 让相机/红外/连接走 mock 分支)。
- 用 `admonition`(`!!! note`)标注 Windows 专属依赖。

- [ ] **Step 3: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add docs/getting-started.md
git commit -m "docs: write getting-started page"
```

---

### Task 3: 核心概念页(架构 + 数据记录)

**Files:**
- Modify: `docs/concepts/architecture.md`、`docs/concepts/data-recording.md`
- 参考源:`HEPiC/__main__.py`(`connect_to_ip`、`grab_status`、`_collect_data`、`on_toggle_play_pause`)、`HEPiC/communications/{tcp_client,klipper_worker,connection_tester}.py`

**Interfaces:**
- Consumes: Task 1 骨架。
- Produces: 两篇背景页,供界面说明页引用。

- [ ] **Step 1: 核对来源**

Read `HEPiC/communications/tcp_client.py`、`HEPiC/communications/klipper_worker.py`、`HEPiC/communications/connection_tester.py`,确认端口、连接流程、采集项。

- [ ] **Step 2: 写 `docs/concepts/architecture.md`**

覆盖:
- 软件(PySide6 桌面端)↔ 平台(树莓派 + Klipper)。
- 两条连接:① TCP 数据服务器(默认 `hepic_port` 10001)收传感器数据;② Moonraker WebSocket(端口 7125)查状态、下发 G-code。
- 连接前自检(`ConnectionTester`)。
- 测试模式 `-t`。
- 链接到 `getting-started.md` 与界面页。

- [ ] **Step 3: 写 `docs/concepts/data-recording.md`**

覆盖(以 `__main__.py` 为准):
- 独立采集线程 `_DataCollectorThread` 按 `data_frequency` 定频采样;UI 刷新(`display_frequency`,≤15)与采样解耦。
- 采集项:`time_s`、目标/实测温度、目标/实测挤出速度、各传感器、`die_diameter_px`(视觉)、`die_temperature_C`(红外)。
- 记录开关 = 主页播放/暂停;CSV 自动存到桌面 `~/Desktop/<时间戳>_autosave.csv`;可同时录像 `<时间戳>_video.mkv`。

- [ ] **Step 4: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/concepts/
git commit -m "docs: write architecture and data-recording concept pages"
```

---

### Task 4: 连接页 + 主页

**Files:**
- Modify: `docs/pages/connection.md`、`docs/pages/home.md`
- 参考源:`HEPiC/tab_widgets/connection_widget.py`;`HEPiC/tab_widgets/home_widget.py` 及其子控件 `command_widget.py`、`data_plot_widget.py`、`platform_status_widget.py`、`vision_widget.py`、`klipper_status_widget.py`

**Interfaces:**
- Consumes: Task 1/3。
- Produces: 两篇界面说明页。

- [ ] **Step 1: 核对来源**

Read `connection_widget.py`、`home_widget.py`、`platform_status_widget.py`、`command_widget.py`、`data_plot_widget.py`、`klipper_status_widget.py`,逐控件确认。

- [ ] **Step 2: 写 `docs/pages/connection.md`**

整页截图占位 + 控件:IP 输入框、连接按钮、自检信息区(白话/技术说明,技术说明里点出连接成功后会建立 TCP+WebSocket 两条连接,链接到架构页)。

- [ ] **Step 3: 写 `docs/pages/home.md`**

整页截图占位 + 逐控件:
- 状态面板(温度设定/实测、挤出速度、模口直径/温度、传感器置零)。
- 模口膨胀 ROI 视图、红外 ROI 视图。
- 实时数据曲线图。
- 命令窗口(手动 G-code + 响应)。
- 挤出/回抽(长按)按钮(技术说明:长按按间隔发小段 `G91/G1 E..`)。
- 播放/暂停(记录开关,链接到数据记录页)、急停按钮。
- Klipper 状态控件(任务进度)。

- [ ] **Step 4: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/pages/connection.md docs/pages/home.md
git commit -m "docs: write connection and home page guides"
```

---

### Task 5: 视觉页 + 红外页

**Files:**
- Modify: `docs/pages/vision.md`、`docs/pages/ir.md`
- 参考源:`HEPiC/tab_widgets/vision_page_widget.py`、`vision_widget.py`、`HEPiC/vision/{video_worker,processing? ,ir_worker}.py`;`HEPiC/tab_widgets/ir_widget.py`;`HEPiC/__main__.py`(`initiate_camera`、`initiate_ir_imager`)

**Interfaces:**
- Consumes: Task 1/3。
- Produces: 两篇界面说明页。

- [ ] **Step 1: 核对来源**

Read `vision_page_widget.py`、`vision_widget.py`、`HEPiC/tab_widgets/ir_widget.py`、`HEPiC/vision/video_worker.py`、`HEPiC/vision/ir_worker.py`,并回看 `__main__.py` 里 `initiate_camera`/`initiate_ir_imager` 的信号连接。

- [ ] **Step 2: 写 `docs/pages/vision.md`**

整页截图占位 + 控件:实时相机画面(Hikrobot)、ROI 框选、曝光调节、黑白反转、模口直径检测(技术说明:ROI 变化发给 video worker 裁剪,处理后得到 `die_diameter_px`)。

- [ ] **Step 3: 写 `docs/pages/ir.md`**

整页截图占位 + 控件:Optris 热像仪画面、温度量程下拉(技术说明:多档量程,换档会重建相机对象)、对焦滑条、ROI、模口出口温度 `die_temperature_C`。

- [ ] **Step 4: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/pages/vision.md docs/pages/ir.md
git commit -m "docs: write vision and IR page guides"
```

---

### Task 6: G-code 页 + 数据处理页

**Files:**
- Modify: `docs/pages/gcode.md`、`docs/pages/data-processor.md`
- 参考源:`HEPiC/tab_widgets/job_sequence_widget.py`、`gcode_widget.py`、`job_sequence_dialog.py`;`HEPiC/tab_widgets/data_processor_widget.py`;`HEPiC/__main__.py`(`handle_gcode_response`、`_extract_software_action`)

**Interfaces:**
- Consumes: Task 1/3。
- Produces: 两篇界面说明页。

- [ ] **Step 1: 核对来源**

Read `job_sequence_widget.py`、`gcode_widget.py`、`data_processor_widget.py`,并回看 `__main__.py` 里 G-code 响应触发的软件动作集合。

- [ ] **Step 2: 写 `docs/pages/gcode.md`**

整页截图占位 + 控件:G-code 文件加载、上传到 Klipper、运行、进度与当前行高亮;
专门一节讲 G-code 响应里的软件动作:`START_RECORDING`/`STOP_RECORDING`/`START_QUALITY_CHECK`/`STOP_QUALITY_CHECK`/`STATUS`/`ZERO_SENSORS`(白话:在 G-code 里写一行注释就能让软件自动开录像/质检等)。

- [ ] **Step 3: 写 `docs/pages/data-processor.md`**

先 Read `data_processor_widget.py` 确认实际控件,再据实编写(加载 CSV、清洗、绘图/导出等以代码为准),逐控件白话/技术说明。

- [ ] **Step 4: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/pages/gcode.md docs/pages/data-processor.md
git commit -m "docs: write gcode and data-processor page guides"
```

---

### Task 7: 质检模式页

**Files:**
- Modify: `docs/pages/quality-check.md`
- 参考源:`HEPiC/tab_widgets/quality_check_widget.py`、`HEPiC/quality_check/{evaluator,materials,gcode}.py`、`HEPiC/database/material_database.py`

**Interfaces:**
- Consumes: Task 1/3。
- Produces: 质检页;wiki 全部页面完成。

- [ ] **Step 1: 核对来源**

Read `quality_check_widget.py`、`HEPiC/quality_check/evaluator.py`、`HEPiC/quality_check/materials.py`、`HEPiC/database/material_database.py`,确认材料库、力范围、稳定性判定。

- [ ] **Step 2: 写 `docs/pages/quality-check.md`**

整页截图占位 + 控件:
- 材料 Family / PI Code 下拉,材料属性(温度、速度、优秀/合格力范围、稳定阈值)。
- 系统信息(实时温度/速度/挤出力英雄数字)。
- 力值指示灯、稳定性指示灯(颜色含义:绿=稳定/合格、黄=警告、红=不稳定/不合格、灰=未知)。
- 挤出进度条、开始/停止质检按钮(技术说明:开始时按材料属性生成质检 G-code 下发)。
- 质检历史、力值曲线图上的合格/优秀区间带。

- [ ] **Step 3: 构建验证**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add docs/pages/quality-check.md
git commit -m "docs: write quality-check page guide"
```

---

### Task 8: 收尾核对

**Files:**
- Modify: 视核对结果而定(链接修正、首页导航补全)。

- [ ] **Step 1: 全站构建 + 本地预览核对**

Run: `.venv/Scripts/mkdocs build --strict` → Expected: PASS。
可选:`.venv/Scripts/mkdocs serve` 本地打开,逐页点链接,确认无断链、每页都有截图占位、每个控件都有白话+技术两层。

- [ ] **Step 2: 核对占位图清单**

确认 `docs/images/` 下需要的截图都在文中以 `![..](../images/<name>.png)` 形式预留,并在 `docs/images/` 放一份 `README` 列出待补图清单。

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: finalize wiki, fix links and list pending screenshots"
```

---

## Self-Review

- **Spec coverage**:spec 的 7 个界面页 + 3 篇背景页 + MkDocs/部署骨架,分别由 Task 4–7(界面)、Task 2–3(背景)、Task 1(骨架/部署)覆盖;截图占位约束贯穿每个写作任务并在 Task 8 汇总。无遗漏。
- **Placeholder scan**:无 TBD;`data-processor.md` 因控件未逐行确认,明确要求实施时先 Read 源码再据实编写(非占位,是必要的核对步骤)。
- **Type consistency**:页面路径、nav 条目、文件名在各任务间一致(`pages/data-processor.md`、`concepts/architecture.md` 等)。
