# Klipper Status Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在连接页右下角和主页右上角各嵌入一个 `KlipperStatusWidget`，显示固件状态、可折叠错误详情，并提供固件重启和 Klipper 软重启按钮。

**Architecture:** 新建可复用的 `KlipperStatusWidget`（独立文件），后端在 `KlipperWorker` 新增 `sigKlipperState` 信号和 `printer_restart()` 方法，并扩展 webhooks 查询。`MainWindow.connect_to_ip()` 负责将 worker 连接到两处 widget 实例。

**Tech Stack:** PySide6, qasync, pytest, pytest-qt, pytest-asyncio

---

## File Map

| 操作 | 文件 |
|------|------|
| 新建 | `HEPiC/tab_widgets/klipper_status_widget.py` |
| 新建 | `test/conftest.py` |
| 新建 | `test/test_klipper_worker_ext.py` |
| 新建 | `test/test_klipper_status_widget.py` |
| 修改 | `HEPiC/communications/klipper_worker.py` |
| 修改 | `HEPiC/tab_widgets/__init__.py` |
| 修改 | `HEPiC/tab_widgets/connection_widget.py` |
| 修改 | `HEPiC/tab_widgets/home_widget.py` |
| 修改 | `HEPiC/__main__.py` |

---

## Task 1: 测试基础设施

**Files:**
- Create: `test/conftest.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 安装测试依赖**

```bash
cd c:/Users/zhengyang/Documents/GitHub/HEPiC
.venv/Scripts/pip install pytest pytest-qt pytest-asyncio
```

Expected: `Successfully installed pytest pytest-qt pytest-asyncio` (版本号不同无影响)

- [ ] **Step 2: 创建 conftest.py**

创建 `test/conftest.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 3: 验证 pytest 能找到测试目录**

```bash
cd c:/Users/zhengyang/Documents/GitHub/HEPiC
.venv/Scripts/python -m pytest test/ --collect-only -q
```

Expected: `no tests ran` 或已有测试列表，没有 import 报错即可。

- [ ] **Step 4: Commit**

```bash
git add test/conftest.py
git commit -m "test: add pytest infrastructure and conftest"
```

---

## Task 2: KlipperWorker 后端扩展

**Files:**
- Modify: `HEPiC/communications/klipper_worker.py`
- Create: `test/test_klipper_worker_ext.py`

- [ ] **Step 1: 写失败测试**

创建 `test/test_klipper_worker_ext.py`：

```python
import asyncio
import pytest
from HEPiC.communications.klipper_worker import KlipperWorker


def test_sigKlipperState_exists(qapp):
    worker = KlipperWorker("localhost", 7125)
    # Signal 必须存在且可连接
    received = []
    worker.sigKlipperState.connect(lambda s, m: received.append((s, m)))
    worker.sigKlipperState.emit("ready", "")
    assert received == [("ready", "")]


def test_webhooks_in_query_objects(qapp):
    worker = KlipperWorker("localhost", 7125)
    # query_klipper 的查询对象必须包含 webhooks
    import inspect, ast
    src = inspect.getsource(worker.query_klipper)
    assert '"webhooks"' in src or "'webhooks'" in src


@pytest.mark.asyncio
async def test_printer_restart_enqueues_correct_message(qapp):
    worker = KlipperWorker("localhost", 7125)
    while not worker.message_queue.empty():
        worker.message_queue.get_nowait()

    # asyncSlot 返回 Task（asyncio.ensure_future），直接 await
    await worker.printer_restart()

    msg = worker.message_queue.get_nowait()
    assert msg["method"] == "printer.restart"
    assert msg["jsonrpc"] == "2.0"
```

- [ ] **Step 2: 运行，确认全部 FAIL**

```bash
cd c:/Users/zhengyang/Documents/GitHub/HEPiC
.venv/Scripts/python -m pytest test/test_klipper_worker_ext.py -v
```

Expected: 3 项 FAIL（`sigKlipperState` 不存在，`webhooks` 不在查询，`printer_restart` 不存在）

- [ ] **Step 3: 修改 klipper_worker.py — 新增信号**

在 `KlipperWorker` 类的信号定义区（`gcode_response = Signal(str)` 之后）添加：

```python
sigKlipperState = Signal(str, str)  # (state, message)
```

- [ ] **Step 4: 修改 klipper_worker.py — 扩展 query_klipper()**

将 `query_klipper` 方法中的 `objects` 字典改为：

```python
"objects": {
    "extruder": None,
    "motion_report": None,
    "virtual_sdcard": None,
    "webhooks": None,
}
```

- [ ] **Step 5: 修改 klipper_worker.py — data_processor 提取 webhooks 状态**

在 `data_processor` 的 `if data["id"] == 2:` 分支末尾（`self.file_position = ...` 之后）添加：

```python
webhooks = sub_msg.get("webhooks", {})
state = webhooks.get("state", "")
message = webhooks.get("state_message", "")
if state:
    self.sigKlipperState.emit(state, message)
```

- [ ] **Step 6: 修改 klipper_worker.py — 新增 printer_restart() 方法**

在 `restart_firmware` 方法之后添加：

```python
@asyncSlot()
async def printer_restart(self):
    self.logger.info("Restarting Klipper ...")
    payload = {
        "jsonrpc": "2.0",
        "method": "printer.restart",
        "id": 6,
    }
    await self.message_queue.put(payload)
```

- [ ] **Step 7: 修改 klipper_worker.py — 将 printer.restart 加入发送白名单**

将 `data_processor` 中的发送白名单改为：

```python
if data["method"] in [
    "printer.gcode.script",
    "printer.objects.subscribe",
    "printer.objects.query",
    "printer.emergency_stop",
    "printer.restart",
]:
```

- [ ] **Step 8: 运行测试，确认全部 PASS**

```bash
.venv/Scripts/python -m pytest test/test_klipper_worker_ext.py -v
```

Expected:
```
test_sigKlipperState_exists PASSED
test_webhooks_in_query_objects PASSED
test_printer_restart_enqueues_correct_message PASSED
```

- [ ] **Step 9: Commit**

```bash
git add HEPiC/communications/klipper_worker.py test/test_klipper_worker_ext.py
git commit -m "feat: add sigKlipperState, printer_restart, webhooks query to KlipperWorker"
```

---

## Task 3: 新建 KlipperStatusWidget

**Files:**
- Create: `HEPiC/tab_widgets/klipper_status_widget.py`
- Create: `test/test_klipper_status_widget.py`

- [ ] **Step 1: 写失败测试**

创建 `test/test_klipper_status_widget.py`：

```python
import pytest
from PySide6.QtCore import Signal, QObject, Qt
from HEPiC.tab_widgets.klipper_status_widget import KlipperStatusWidget


def test_initial_state_buttons_disabled(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    assert not w._firmware_btn.isEnabled()
    assert not w._klipper_btn.isEnabled()


def test_initial_toggle_btn_hidden(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    assert not w._toggle_btn.isVisible()
    assert not w._detail_label.isVisible()


def test_on_state_changed_ready(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.on_state_changed("ready", "")
    assert w._state_label.text() == "ready"
    assert not w._toggle_btn.isVisible()


def test_on_state_changed_error_shows_toggle(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.on_state_changed("error", "MCU shutdown: Timer too close")
    assert w._state_label.text() == "error"
    assert w._toggle_btn.isVisible()
    assert w._detail_label.text() == "MCU shutdown: Timer too close"
    assert not w._detail_label.isVisible()  # 折叠，默认不展开


def test_toggle_expands_and_collapses(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.on_state_changed("error", "some error")
    assert not w._detail_label.isVisible()
    qtbot.mouseClick(w._toggle_btn, Qt.LeftButton)
    assert w._detail_label.isVisible()
    qtbot.mouseClick(w._toggle_btn, Qt.LeftButton)
    assert not w._detail_label.isVisible()


class _MockWorker(QObject):
    sigKlipperState = Signal(str, str)
    def restart_firmware(self): pass
    def printer_restart(self): pass


def test_connect_worker_enables_buttons(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    mock_worker = _MockWorker()
    w.connect_worker(mock_worker)
    assert w._firmware_btn.isEnabled()
    assert w._klipper_btn.isEnabled()


def test_connect_worker_receives_state(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    mock_worker = _MockWorker()
    w.connect_worker(mock_worker)
    mock_worker.sigKlipperState.emit("shutdown", "Printer shutdown")
    assert w._state_label.text() == "shutdown"
    assert w._toggle_btn.isVisible()
```

- [ ] **Step 2: 运行，确认全部 FAIL**

```bash
.venv/Scripts/python -m pytest test/test_klipper_status_widget.py -v
```

Expected: 全部 FAIL（`KlipperStatusWidget` 不存在）

- [ ] **Step 3: 创建 KlipperStatusWidget**

创建 `HEPiC/tab_widgets/klipper_status_widget.py`：

```python
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Slot

_STATE_COLORS = {
    "ready":    "#4CAF50",
    "startup":  "#FF9800",
    "shutdown": "#9E9E9E",
    "error":    "#F44336",
}


class KlipperStatusWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #9E9E9E; font-size: 16px;")

        self._state_label = QLabel("未连接")

        self._toggle_btn = QPushButton("▼ 详情")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setVisible(False)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self._dot)
        status_row.addWidget(self._state_label)
        status_row.addStretch()
        status_row.addWidget(self._toggle_btn)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setVisible(False)

        self._firmware_btn = QPushButton("固件重启")
        self._firmware_btn.setEnabled(False)
        self._klipper_btn = QPushButton("Klipper 重启")
        self._klipper_btn.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self._firmware_btn)
        btn_row.addWidget(self._klipper_btn)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(status_row)
        layout.addWidget(self._detail_label)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self._toggle_btn.clicked.connect(self._toggle_detail)

    def connect_worker(self, worker):
        worker.sigKlipperState.connect(self.on_state_changed)
        self._firmware_btn.clicked.connect(worker.restart_firmware)
        self._klipper_btn.clicked.connect(worker.printer_restart)
        self._firmware_btn.setEnabled(True)
        self._klipper_btn.setEnabled(True)

    @Slot(str, str)
    def on_state_changed(self, state: str, message: str):
        color = _STATE_COLORS.get(state, "#9E9E9E")
        self._dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self._state_label.setText(state)
        self._detail_label.setText(message)
        has_message = bool(message.strip())
        self._toggle_btn.setVisible(has_message)
        if not has_message:
            self._detail_label.setVisible(False)
            self._toggle_btn.setText("▼ 详情")

    def _toggle_detail(self):
        visible = not self._detail_label.isVisible()
        self._detail_label.setVisible(visible)
        self._toggle_btn.setText("▲ 详情" if visible else "▼ 详情")
```

- [ ] **Step 4: 运行测试，确认全部 PASS**

```bash
.venv/Scripts/python -m pytest test/test_klipper_status_widget.py -v
```

Expected:
```
test_initial_state_buttons_disabled PASSED
test_initial_toggle_btn_hidden PASSED
test_on_state_changed_ready PASSED
test_on_state_changed_error_shows_toggle PASSED
test_toggle_expands_and_collapses PASSED
test_connect_worker_enables_buttons PASSED
test_connect_worker_receives_state PASSED
```

- [ ] **Step 5: Commit**

```bash
git add HEPiC/tab_widgets/klipper_status_widget.py test/test_klipper_status_widget.py
git commit -m "feat: add KlipperStatusWidget"
```

---

## Task 4: 导出 + 嵌入 ConnectionWidget 和 HomeWidget

**Files:**
- Modify: `HEPiC/tab_widgets/__init__.py`
- Modify: `HEPiC/tab_widgets/connection_widget.py`
- Modify: `HEPiC/tab_widgets/home_widget.py`

- [ ] **Step 1: 在 `__init__.py` 导出新 widget**

在 `HEPiC/tab_widgets/__init__.py` 末尾添加：

```python
from .klipper_status_widget import KlipperStatusWidget
```

- [ ] **Step 2: 修改 ConnectionWidget — 导入并实例化**

在 `connection_widget.py` 顶部 import 区添加：

```python
from .klipper_status_widget import KlipperStatusWidget
```

在 `__init__` 的组件创建区（`self.self_test = QLabel("...")` 之后）添加：

```python
self.klipper_status_widget = KlipperStatusWidget()
```

- [ ] **Step 3: 修改 ConnectionWidget — 重构底部布局**

将现有布局代码：

```python
message_layout = QHBoxLayout()
message_layout.addWidget(self.self_test)
layout.addLayout(ip_layout)
layout.addStretch(1)
layout.addLayout(message_layout)
```

替换为：

```python
bottom_layout = QHBoxLayout()
bottom_layout.addWidget(self.self_test)
bottom_layout.addStretch()
bottom_layout.addWidget(self.klipper_status_widget)
layout.addLayout(ip_layout)
layout.addStretch(1)
layout.addLayout(bottom_layout)
```

- [ ] **Step 4: 修改 HomeWidget — 导入并实例化**

在 `home_widget.py` 顶部 import 区添加（在现有 from .xxx import 语句之后）：

```python
from .klipper_status_widget import KlipperStatusWidget
```

在 `__init__` 的组件创建区（`self.retract_button = QPushButton("回抽 10 mm")` 之后）添加：

```python
self.klipper_status_widget = KlipperStatusWidget()
```

- [ ] **Step 5: 修改 HomeWidget — 在 data_layout 顶部插入 klipper_status_widget**

将现有布局代码：

```python
data_layout = QVBoxLayout()
status_and_vision_layout = QHBoxLayout()
status_and_vision_layout.addWidget(self.status_widget)
status_and_vision_layout.addWidget(self.dieswell_widget)
status_and_vision_layout.addWidget(self.ir_roi_widget)
data_layout.addLayout(status_and_vision_layout)
data_layout.addWidget(self.data_widget)
```

替换为：

```python
data_layout = QVBoxLayout()
klipper_row = QHBoxLayout()
klipper_row.addStretch()
klipper_row.addWidget(self.klipper_status_widget)
data_layout.addLayout(klipper_row)
status_and_vision_layout = QHBoxLayout()
status_and_vision_layout.addWidget(self.status_widget)
status_and_vision_layout.addWidget(self.dieswell_widget)
status_and_vision_layout.addWidget(self.ir_roi_widget)
data_layout.addLayout(status_and_vision_layout)
data_layout.addWidget(self.data_widget)
```

- [ ] **Step 6: 运行全部测试，确认无回归**

```bash
.venv/Scripts/python -m pytest test/test_klipper_status_widget.py test/test_klipper_worker_ext.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add HEPiC/tab_widgets/__init__.py HEPiC/tab_widgets/connection_widget.py HEPiC/tab_widgets/home_widget.py
git commit -m "feat: embed KlipperStatusWidget in ConnectionWidget and HomeWidget"
```

---

## Task 5: 在 MainWindow 接线

**Files:**
- Modify: `HEPiC/__main__.py`

- [ ] **Step 1: 在 connect_to_ip 中调用 connect_worker**

在 `connect_to_ip` 方法中，找到现有信号连接的末尾（`self.home_widget.sigRetract.connect(self.klipper_worker.send_gcode)` 之后），添加：

```python
self.connection_widget.klipper_status_widget.connect_worker(self.klipper_worker)
self.home_widget.klipper_status_widget.connect_worker(self.klipper_worker)
```

- [ ] **Step 2: 运行全部测试**

```bash
.venv/Scripts/python -m pytest test/test_klipper_status_widget.py test/test_klipper_worker_ext.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: 手动验证（如有设备可连接）**

启动 app，进入连接页，检查右下角是否出现 `● 未连接 [固件重启(disabled)] [Klipper重启(disabled)]`。  
连接成功后，检查按钮是否变为 enabled，状态是否变为 `● ready`（绿色）。  
如有固件报错，检查 `▼ 详情` 按钮是否可见，点击后是否展开错误消息。

- [ ] **Step 4: Commit**

```bash
git add HEPiC/__main__.py
git commit -m "feat: wire KlipperStatusWidget to KlipperWorker in MainWindow"
```
