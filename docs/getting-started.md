# 快速开始

本页介绍如何从零开始安装 HEPiC，并首次启动软件。  
全程大约需要 **15–30 分钟**（取决于网速与 SDK 安装速度）。

---

## 系统要求

- **操作系统：** Windows 10/11（64 位）
- **Python：** 3.12 或更高版本
- **硬件（可选）：** Hikrobot 工业相机、Optris 红外热像仪、基于 Raspberry Pi 的挤出平台（Klipper）

---

## 第一步：安装外部依赖

!!! note "Windows 专属依赖"
    以下三个依赖均为 Windows 平台专属。Hikrobot SDK 和 Optris SDK 提供原生驱动与动态链接库，必须在安装 Python 包之前完成安装，否则 HEPiC 在启动时将无法加载相机驱动。

### 1. Hikrobot 机器视觉 SDK

Hikrobot SDK 为工业相机提供底层驱动与 Python 绑定。

1. 访问 [Hikrobot 官方下载页](https://www.hikrobotics.com/en/machinevision/service/download/)
2. 下载并安装适用于 Windows 的最新版 Machine Vision SDK
3. 安装完成后**重启计算机**以确保驱动生效

### 2. Optris 红外热像仪 SDK

Optris SDK 为 Optris Xi 系列红外热像仪提供驱动。

1. 访问 [Optris SDK GitHub 仓库](https://github.com/Optris/otcsdk_downloads)
2. 下载并安装适用于 Windows 的 SDK
3. 安装完成后确认热像仪驱动正常识别

### 3. FFmpeg

FFmpeg 用于视频录制与时间推移（timelapse）视频编码。

在 **Windows Terminal** 或 **PowerShell** 中执行：

```powershell
winget install ffmpeg
```

安装完成后，新开一个终端窗口并运行 `ffmpeg -version` 确认安装成功。

---

## 第二步：克隆仓库

```bash
git clone https://github.com/zloverty/HEPiC.git
cd HEPiC
```

---

## 第三步：创建虚拟环境

在 `HEPiC` 文件夹内创建并激活 venv：

```powershell
python -m venv .venv
.venv\Scripts\activate
```

激活成功后，终端提示符前会出现 `(.venv)` 前缀。

---

## 第四步：安装 HEPiC

在已激活的 venv 中执行：

```powershell
pip install .
```

此命令会读取 `pyproject.toml`，自动安装所有 Python 依赖（PySide6、pyqtgraph、OpenCV、qasync 等），并将 `hepic` 命令注册为可执行入口。

---

## 第五步：启动软件

安装完成后，直接在终端输入：

```powershell
hepic
```

软件启动后会先显示**连接页**，要求输入 Raspberry Pi 的 IP 地址和端口，然后自动检测相机与红外热像仪。

---

## 测试模式（无硬件启动）

如果你暂时没有连接任何硬件，可以使用测试模式打开界面进行功能演示：

```powershell
hepic -t
```

**白话说明：** 加上 `-t` 参数，软件在没有实体相机、红外仪或平台连接的情况下也能正常打开界面，可以浏览各功能页面、熟悉操作逻辑。

**技术说明：** `-t` / `--test` 标志由 `argparse` 解析，并将 `test_mode=True` 传入 `MainWindow`。在此模式下，相机初始化（`VideoWorker`）走 mock 分支读取测试图像，红外热像仪初始化（`IRWorker`）被静默跳过，网络连接测试（`ConnectionTester`）同样走 mock 分支，从而绕过所有对物理硬件的依赖，不影响 GUI 渲染与逻辑演示。

---

## 常见问题

**Q：运行 `hepic` 时提示"找不到命令"**

确认当前终端已激活 venv（提示符前有 `(.venv)`），且 `pip install .` 已成功完成。

**Q：Hikrobot 相机初始化失败**

检查 Hikrobot SDK 是否正确安装，相机 USB/GigE 连接是否正常，并尝试重启计算机。若仅用于演示，可使用 `hepic -t` 跳过相机初始化。

**Q：FFmpeg 未找到**

关闭当前终端后重新打开，或手动检查 `ffmpeg` 是否在系统 PATH 中：`where ffmpeg`。
