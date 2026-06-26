# 连接页

连接页是 HEPiC 启动后显示的第一个界面，用于输入树莓派的 IP 地址并发起与挤出平台的连接。

![连接页整体截图](../images/connection-page.png)

---

## 控件说明

### IP 地址输入框

**白话**：在这里填写树莓派的 IP 地址（例如 `192.168.0.81`）。如果你的网络环境没有变化，上次使用的地址会自动填入，无需重新输入。

**技术说明**：对应 `ConnectionWidget.ip_input`（`QLineEdit`）。初始值从 `config.json` 的 `hepic_host` 字段读取。按下 Enter 键与点击"连接"按钮等效，两者均触发 `on_connect_clicked` 槽。

---

### 连接按钮

**白话**：填好 IP 地址后，点击此按钮开始连接树莓派。连接过程会自动执行一套自检，你可以在下方的状态信息区看到进度。连接成功后，按钮变为灰色（不可点击），软件自动跳转到主页。

**技术说明**：对应 `ConnectionWidget.connect_button`（`QPushButton`，标签"连接"）。点击后：

1. 读取输入框中的 IP 字符串，通过 `host` 信号传递给主窗口。
2. 主窗口调用 `ConnectionTester` 执行 4 步自检（Ping → TCP 端口 → Moonraker HTTP → Klipper 状态）。
3. 全部通过后，同时建立 **TCP 数据连接**（端口 10001）和 **Moonraker WebSocket 连接**（端口 7125）。详见[软件架构](../concepts/architecture.md)。
4. 连接成功时，`update_button_status("连接成功")` 被调用，按钮禁用；失败时按钮保持可用，可再次尝试。

---

### 自检信息区

**白话**：连接过程中，这里会逐行显示每一步自检的结果，例如"Ping 成功"、"TCP 端口可达"、"Moonraker 在线"等。如果某步失败，错误原因也会在这里显示，帮助你判断是网络问题还是服务未启动。

**技术说明**：对应 `ConnectionWidget.self_test`（`QLabel`）。内部维护一个长度为 10 的双端队列（`deque(maxlen=10)`），每次收到新状态字符串时追加并刷新显示。`ConnectionTester` 通过 `test_msg` 信号驱动更新，显示最近 10 条自检消息。

---

## 连接失败时怎么办？

| 自检步骤失败 | 可能原因 | 建议操作 |
|---|---|---|
| Ping 失败 | 树莓派未上电或不在同一网络 | 检查树莓派电源和网线/WiFi |
| TCP 端口不可达 | hepic_server 未启动 | 登录树莓派，确认服务在端口 10001 监听 |
| Moonraker 无响应 | Moonraker 服务未启动 | 在树莓派上重启 Moonraker 服务 |
| Klipper 未连接 | Klipper 串口断开或固件崩溃 | 主页提供"固件重启"和"Klipper 重启"按钮 |

!!! note "测试模式"
    使用 `hepic -t` 启动时，自检在 TCP 端口通过后直接跳过 Moonraker 和 Klipper 检查，无需真实平台即可进入主界面。详见[软件架构 → 测试模式](../concepts/architecture.md)。
