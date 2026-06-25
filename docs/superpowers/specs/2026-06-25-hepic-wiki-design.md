# HEPiC 用户 Wiki — 设计文档

日期:2026-06-25
状态:已批准,待实施

## 目标

为 HEPiC(Hotend Extrusion Platform 控制软件)编写一套**面向用户**的 wiki,
从 GUI 使用者的视角解释软件里每一个组件的功能。每个控件用**两层语言**讲解:

- **白话**:一句话说清它是做什么的、什么时候用。
- **技术说明**:它在底层做了什么(发什么信号 / G-code、连到哪个 worker、读哪个传感器),
  只在必要时点到为止,不深入实现细节。

不需要做到 API / 逐类级别的底层文档,重点是用户能看懂、会用。

## 形式与技术栈

- 静态站点:**MkDocs + Material 主题**。
- 部署:**GitHub Pages**,通过 GitHub Actions 自动构建。
- 语言:**中文为主**(与代码内中文注释风格一致)。
- 截图:在每页该放图的位置写好图说明并**预留占位**(如 `![主页](../images/home.png)`),
  由维护者以后自行补图。

## 目录结构

```
mkdocs.yml                  # 导航、主题、搜索配置
docs/
  index.md                  # 这是什么 / 一张架构总览图
  getting-started.md        # 安装、依赖、启动、测试模式 -t
  concepts/
    architecture.md         # 软件↔树莓派 的连接结构(TCP 数据 + Klipper/Moonraker)
    data-recording.md       # 数据怎么采集、CSV 自动保存、录像
  pages/                    # 主体:按 GUI 标签页组织,每页一篇
    connection.md           # 连接页
    home.md                 # 主页
    vision.md               # 视觉页
    ir.md                   # 红外页
    gcode.md                # G-code 页
    data-processor.md       # 数据处理页
    quality-check.md        # 质检模式
  images/                   # 截图占位目录(.gitkeep 占位)
.github/workflows/docs.yml  # 自动部署到 GitHub Pages
```

## 每页统一写法

1. 页面开头:一句"这个标签页是做什么的" + 整页截图占位。
2. 逐个控件展开,统一模板:

   > ### 控件名(例:急停按钮 🛑)
   > **白话**:……
   > **技术说明**:……(必要时)

## 各页面内容范围(以代码为准)

### concepts/architecture.md
- 软件 = PySide6 桌面端;平台 = 树莓派 + Klipper。
- 两条连接:① TCP 数据服务器(默认端口 10001)接收传感器数据;
  ② 通过 Moonraker 的 WebSocket(默认端口 7125)查询状态、下发 G-code。
- 连接前的自检流程(ConnectionTester)。
- 测试模式 `-t`:跳过硬件,便于演示。

### concepts/data-recording.md
- 数据采集线程按 `data_frequency` 定频采样,UI 刷新与采样解耦。
- 采集项:目标/实测温度、目标/实测挤出速度、时间、各传感器、模口直径(视觉)、模口温度(红外)。
- 录制开关 = 主页播放/暂停按钮;CSV 自动保存到桌面;可同时录像(mkv)。

### pages/connection.md
- IP 输入框、连接按钮、自检信息区。

### pages/home.md
- 状态面板(PlatformStatusWidget):温度设定/实测、挤出速度、模口直径/温度、传感器置零。
- 模口膨胀 ROI 视图、红外 ROI 视图。
- 实时数据曲线图(DataPlotWidget)。
- 命令窗口(CommandWidget):手动发 G-code、查看响应。
- 挤出 / 回抽(长按)按钮。
- 播放/暂停(记录开关)、急停按钮。
- Klipper 状态控件(KlipperStatusWidget):打印任务进度等。

### pages/vision.md
- 实时相机画面(Hikrobot)、ROI 框选、曝光调节、黑白反转、模口直径检测。

### pages/ir.md
- Optris 红外热像仪画面、温度量程下拉、对焦滑条、ROI、模口出口温度。

### pages/gcode.md
- G-code 文件加载、上传到 Klipper、运行、进度与当前行高亮。
- G-code 响应里的软件动作(START_RECORDING / STOP_RECORDING /
  START_QUALITY_CHECK / STOP_QUALITY_CHECK / STATUS / ZERO_SENSORS)。

### pages/data-processor.md
- 数据后处理页(以实际控件为准:加载 CSV、清洗、绘图/导出)。

### pages/quality-check.md
- 材料 Family / PI Code 选择,材料属性(温度、速度、力范围、稳定阈值)。
- 系统信息(实时温度/速度/挤出力)、力值与稳定性指示灯、挤出进度条。
- 开始/停止质检、质检历史、力值合格/优秀区间带。

## 不做(YAGNI)

- 不做逐文件、逐类的 API 参考。
- 不做开发者贡献指南、打包发布流程(除非以后单独要求)。
- 不自动生成截图(无法运行 GUI)。

## 实施顺序

1. 搭好 MkDocs 骨架(mkdocs.yml、依赖、Actions、images 占位)。
2. 写背景页(index、getting-started、concepts/*)。
3. 按标签页逐篇写 pages/*,每篇前重新核对对应 widget 代码。
