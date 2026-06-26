# HEPiC 使用手册

## 什么是 HEPiC？

**HEPiC**（Hotend Extrusion Platform intelligent Controller）是一款基于树莓派的热端挤出平台控制软件，专为 FDM（熔融沉积成型）过程中相关量的同步测量而设计。

通过 HEPiC，您可以：

- **连接树莓派平台** — 通过网络与 Klipper 固件通信，实时控制挤出机
- **实时监控** — 同步采集温度、挤出力、视觉图像和红外热像数据
- **执行 G-code** — 直接在软件内编写并运行 G-code 指令
- **记录数据** — 将实验过程中的所有传感器数据自动记录到本地文件
- **材料质检** — 在质检模式下对挤出材料进行在线评估

## 架构总览

![架构总览](images/architecture-overview.png)

## 快速导航

| 入门 | 界面说明 |
|------|----------|
| [快速开始](getting-started.md) — 安装、连接到平台并完成第一次测量 | [连接页](pages/connection.md) — 配置并建立与树莓派的连接 |
| [软件架构](concepts/architecture.md) — 了解软件的整体设计思路 | [主页](pages/home.md) — 主控制面板说明 |
| [数据记录](concepts/data-recording.md) — 了解数据如何保存和组织 | [视觉页](pages/vision.md) / [红外页](pages/ir.md) — 图像与热成像 |

---

!!! tip "初次使用？"
    建议从 [快速开始](getting-started.md) 开始，5 分钟内完成安装并连接到平台。
