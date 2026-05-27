# Klipper 状态 Widget 设计文档

**日期：** 2026-05-27  
**状态：** 已批准

---

## 目标

在连接页（右下角）和主页（右上角）各嵌入一个 `KlipperStatusWidget`，提供：
- 固件状态指示（颜色 + 文字）
- 可折叠的错误详情
- 固件重启（`FIRMWARE_RESTART`）按钮
- Klipper 软重启（`printer.restart`）按钮

---

## 后端：KlipperWorker 改动

文件：`HEPiC/communications/klipper_worker.py`

### 新增信号

```python
sigKlipperState = Signal(str, str)  # (state, message)
# state 取值: "ready" | "startup" | "shutdown" | "error"
# message: 错误时的详情字符串，正常时为空字符串
```

### 扩展 query_klipper()

在查询对象中新增 `webhooks`：

```python
"objects": {
    "extruder": None,
    "motion_report": None,
    "virtual_sdcard": None,
    "webhooks": None   # 新增
}
```

在 `data_processor` 处理 `id == 2` 的 result 时，提取并 emit：

```python
webhooks = sub_msg.get("webhooks", {})
state = webhooks.get("state", "")
message = webhooks.get("state_message", "")
if state:
    self.sigKlipperState.emit(state, message)
```

### 新增 printer_restart()

```python
@asyncSlot()
async def printer_restart(self):
    payload = {
        "jsonrpc": "2.0",
        "method": "printer.restart",
        "id": 6
    }
    await self.message_queue.put(payload)
```

同时在 `data_processor` 出队发送白名单中加入 `"printer.restart"`：

```python
if data["method"] in [
    "printer.gcode.script",
    "printer.objects.subscribe",
    "printer.objects.query",
    "printer.emergency_stop",
    "printer.restart",        # 新增
]:
    await websocket.send(json.dumps(data))
```

---

## 新组件：KlipperStatusWidget

文件：`HEPiC/tab_widgets/klipper_status_widget.py`

### 视觉结构

```
┌─────────────────────────────────────────┐
│  ● ready          [▼ 详情]              │  ← 状态行
├─────────────────────────────────────────┤
│  (折叠区，默认隐藏)                      │
│  MCU 'mcu' shutdown: Timer too close    │  ← 错误详情 QLabel
└─────────────────────────────────────────┘
  [固件重启]  [Klipper 重启]               ← 按钮行
```

### 状态颜色映射

| state      | 颜色 |
|------------|------|
| `ready`    | 绿色 |
| `startup`  | 橙色 |
| `shutdown` | 灰色 |
| `error`    | 红色 |
| 未连接     | 灰色 |

### 接口

```python
class KlipperStatusWidget(QWidget):

    def connect_worker(self, worker: KlipperWorker):
        """连接 worker 信号，启用按钮。"""
        worker.sigKlipperState.connect(self.on_state_changed)
        self._firmware_btn.clicked.connect(worker.restart_firmware)
        self._klipper_btn.clicked.connect(worker.printer_restart)
        self._firmware_btn.setEnabled(True)
        self._klipper_btn.setEnabled(True)

    @Slot(str, str)
    def on_state_changed(self, state: str, message: str):
        """更新状态指示器和折叠详情。"""
        # 更新颜色点和文字
        # 有 message 时显示 [▼ 详情] 按钮，否则隐藏
        # 更新 detail label 文本
```

### 行为细节

- `[▼ 详情]` 切换按钮仅在 `message` 非空时可见
- 详情区默认折叠；点击切换展开/收起
- 两个重启按钮默认 `disabled`，`connect_worker()` 后才启用

---

## 布局嵌入

### ConnectionWidget（底部右下角）

文件：`HEPiC/tab_widgets/connection_widget.py`

当前底部是单独一行 `self_test` label。改为底部 `QHBoxLayout`，左边保留 `self_test`，右边放 `KlipperStatusWidget`：

```
┌──────────────────────────────────────────────────────┐
│  [IP 地址输入框]                    [连接]            │
│                                                      │
│  (stretch)                                           │
│                                                      │
│  连接中...          ● ready   [固件重启] [Klipper重启]│
└──────────────────────────────────────────────────────┘
```

### HomeWidget（右列顶部）

文件：`HEPiC/tab_widgets/home_widget.py`

在右列 `data_layout` 顶部插入 `KlipperStatusWidget`，使用 `Qt.AlignRight` 右对齐：

```
右列（data_layout）：
┌──────────────────────────────────────────────────────┐
│                  ● ready   [固件重启] [Klipper重启]   │  ← 新增顶行
├──────────────────────────────────────────────────────┤
│  [状态面板]  [熔体图像]  [红外图像]                   │
│  [数据图表]                                          │
└──────────────────────────────────────────────────────┘
```

### MainWindow（connect_to_ip）

文件：`HEPiC/__main__.py`

在 `klipper_worker` 创建并就绪后，连接两处 widget：

```python
self.connection_widget.klipper_status_widget.connect_worker(self.klipper_worker)
self.home_widget.klipper_status_widget.connect_worker(self.klipper_worker)
```

### __init__.py 导出

文件：`HEPiC/tab_widgets/__init__.py`

新增导出：
```python
from .klipper_status_widget import KlipperStatusWidget
```

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `HEPiC/communications/klipper_worker.py` | 修改：新增信号、扩展查询、新增 printer_restart |
| `HEPiC/tab_widgets/klipper_status_widget.py` | **新建** |
| `HEPiC/tab_widgets/__init__.py` | 修改：新增导出 |
| `HEPiC/tab_widgets/connection_widget.py` | 修改：底部布局 + 嵌入 widget |
| `HEPiC/tab_widgets/home_widget.py` | 修改：右列顶部 + 嵌入 widget |
| `HEPiC/__main__.py` | 修改：connect_to_ip 中调用 connect_worker |
