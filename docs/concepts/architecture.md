# 软件架构

本页说明 HEPiC 桌面端与树莓派挤出平台之间的整体连接关系，帮助你理解"软件在做什么、信号走哪条路"。

---

## 整体结构

HEPiC 是一个运行在 Windows PC 上的 **PySide6 桌面应用**。它与位于树莓派上的挤出平台建立**两条独立的连接**，分别承担不同职责：

| 连接 | 协议 | 默认端口 | 职责 |
|------|------|---------|------|
| 数据服务器（hepic_server） | TCP（JSON 行协议） | **10001** | 实时接收传感器数据 |
| Moonraker WebSocket | WebSocket | **7125** | 查询 Klipper 状态、下发 G-code |

```
Windows PC（HEPiC）
  │
  ├─── TCP ──────────────────────▶  树莓派 :10001  (hepic_server)
  │                                  传感器数据流（JSON）
  │
  └─── WebSocket ─────────────▶  树莓派 :7125   (Moonraker)
                                   G-code 指令 / 状态查询
```

---

## 连接 1：TCP 数据服务器

**白话：** 树莓派上运行一个自定义的数据采集服务，通过 TCP 长连接把传感器数值（力、位移、计米等）源源不断推送给 PC。

**技术说明：** `TCPClient` 在独立的 asyncio 任务中持续监听来自 `{host}:10001` 的 JSON 行数据。每条消息包含 `message_type` 字段（`sensor_config` 或 `sensor_data`）。

- 连接成功后，客户端首先发送 `get_sensor_config` 请求，获取该平台当前配置了哪些传感器（名称、是否可归零等）。
- 此后每条 `sensor_data` 消息的 `payload` 包含各传感器的最新读数。
- 若超过 3 秒未收到数据，或连接中断，`TCPClient` 会自动以指数退避策略重连（初始间隔 1 s，最长 30 s）。
- 断线期间，所有传感器值被标记为 `NaN`，避免 UI 显示过时数据。

---

## 连接 2：Moonraker WebSocket

**白话：** Moonraker 是 Klipper 的 HTTP / WebSocket 前端。HEPiC 通过它查询打印机当前温度、挤出速度等状态，也通过它把 G-code 指令（如加热、挤出）发给 Klipper 执行。

**技术说明：** `KlipperWorker` 通过 `ws://{host}:7125/websocket` 与 Moonraker 建立 WebSocket 连接，采用 JSON-RPC 2.0 协议：

- **状态查询**：定期（默认间隔 0.1 s）发送 `printer.objects.query`，订阅 `extruder`（温度）、`motion_report`（实时挤出速度）、`virtual_sdcard`（进度）、`webhooks`（Klipper 状态）等对象。
- **G-code 下发**：通过 `printer.gcode.script` 方法把 G-code 字符串发送给 Klipper 执行；支持急停（`printer.emergency_stop`）和固件重启（`printer.firmware_restart`）。
- 连接异常时同样以指数退避策略自动重连。

---

## 连接前自检（ConnectionTester）

每次点击"连接"后，HEPiC 不会直接建立工作连接，而是先运行一套 **4 步自检流程**，确认网络环境与服务状态正常：

1. **[1/4] Ping 主机** — 确认树莓派在网络上可达。
2. **[2/4] 检查 TCP 数据端口** — 确认 hepic_server 在 `:10001` 上已启动并监听。
3. **[3/4] 检查 Moonraker 服务** — 向 `http://{host}:7125/server/info` 发送 HTTP 请求，确认 Moonraker 在线并取回 Klipper 状态信息。
4. **[4/4] 检查 Klipper 连接** — 从步骤 3 的响应中确认 Klipper 服务已连接（`klippy_connected: true`）；注意：不要求 Klipper 处于 `ready` 状态，因为主页提供重启按钮，可在 `shutdown` / `error` 等状态下恢复。

任何一步失败，自检终止并在连接页显示错误原因；全部通过后，自动进入 `connect_to_ip` 同时建立 TCP 与 WebSocket 连接。

!!! note "测试模式下的自检"
    使用 `hepic -t` 启动时，自检会在步骤 2（TCP 端口检查）通过后直接跳过步骤 3 和 4，无需运行中的 Moonraker / Klipper 即可进入主界面。详情参见[快速开始 → 测试模式](../getting-started.md)。

---

## 测试模式（`-t`）

```powershell
hepic -t
```

**白话：** 加 `-t` 启动后，不需要树莓派在线就能打开界面、浏览各功能页。

**技术说明：** `--test` 标志使以下行为变化：

- `ConnectionTester` 跳过 Moonraker / Klipper 检查（见上文）。
- `KlipperWorker` 跳过 WebSocket 连接，不向 Moonraker 发送任何请求。
- 相机与红外热像仪初始化失败时不报错，GUI 仍可正常打开；但不会有实时数据。

---

## 相关页面

- 首次连接操作步骤 → [快速开始](../getting-started.md)
- 连接页界面说明 → [界面说明 / 连接页](../pages/connection.md)
- 主页（数据显示与记录控制）→ [界面说明 / 主页](../pages/home.md)
