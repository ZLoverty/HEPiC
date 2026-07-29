# 更新日志

## v1.6.0

### 质检模式

- **归零逻辑改为服务端 tare，而非客户端本地扣减偏移**：`zero_sensor()` 不再在本地记录 `offset` 并本地做减法，而是向 hepic_server 发送 `{"action": "zero", "sensor": ...}` 请求，由仪器端对传感器硬件执行 tare；客户端收到 `zero_result` 消息后仅记录成功/失败，广播出来的数值本身已经是归零后的值。这样多个终端同时连接同一套传感器时，看到的力值是一致的，不会出现各终端各自维护一份本地偏移导致互相不同步的问题。
- **停止质检按钮改为通过急停 + 固件重启中止**：质检的 gcode 是一次性发送给 Klipper 执行的脚本，没有取消/暂停机制；点击停止后会触发 `emergency_stop()` 清空运动队列并终止执行，随后 `restart_firmware()` 让 Klipper 从 shutdown 恢复到 ready，替代此前"停止按钮点了但挤出还在继续"的问题。
- **质检过程消息更细化**：在加热、回抽、归零、补偿挤出、正式质检、质检完毕等阶段之间插入更明确的 `M118 STATUS` 提示，并在归零、补偿挤出后增加等待时间，减小机械抖动对结果的影响；`STOP_QUALITY_CHECK` 改为在挤出完全稳定后发送，不再由固件重启（而是显式等待）来结束质检窗口。
- **修复评估阶段在样本中出现 NaN/Inf 时报错 `'float' object has no attribute 'numerator'` 的问题**：`evaluate_force_window()` 在取最近窗口样本时过滤掉非有限值（`math.isfinite`），过滤后样本数不足 10 个则直接返回 `None`，不再让 `pstdev` 处理含 NaN/Inf 的数据。
- **日志新增可归零传感器列表**：连接建立、收到传感器配置时均打印当前可归零（`can_zero`）的传感器名称，便于排查归零请求为什么没有生效。

### 界面与交互

- **新增设置菜单**：新增 `SettingsDialog`，根据 `config.json` 中每个键的值类型自动生成对应控件（颜色选择器、数值输入框、路径浏览器、复选框、文本框），目前是初版原型，后续还有较大改进空间。
- **设置菜单集成更新日志**：新增 `HEPiC/CHANGELOG.md`，通过 `find_bundled_file()`（只读，始终读取当前安装版本自带的文件，不像 `find_app_file()` 那样拷贝到 `~/.HEPiC/` 后可能读到旧版本缓存）读取并在设置菜单中展示。
- **新增"许愿池"入口**：设置菜单新增反馈/需求提交入口，弹窗展示二维码（按屏幕 DPI 缩放，避免 Retina 下模糊）及飞书表单链接。
- **录制视频改为可选项**：设置菜单新增"保存视频"开关，可关闭延时摄影的视频保存。
- **按下录制按钮时弹出保存路径提示条**：新增顶部横幅，展示当前保存目录，并提供"打开文件夹""修改路径"按钮及自动淡出关闭，避免新用户不清楚数据存到哪里，同时不需要每次都用阻塞式对话框打断操作。（感谢反馈@陶瑶）
- **标签栏在 macOS 上强制左上对齐**：新增 `_TopAlignedTabBarStyle`，覆盖 `SH_TabBar_Alignment` 样式提示；此前 macOS 原生样式会把 West 方向的标签栏在垂直方向居中，与 Windows/Fusion 样式表现不一致。

### 相机驱动

- **Hikvision (`hikcam_win.py`) 与 Optris (`optris_camera.py` / `ir_worker.py`) 驱动整体重构日志与异常处理**：`print` 全部替换为 `logging`；新增 `HikCameraError` 等专用异常类型替代裸 `Exception`；SDK 导入失败时不再吞掉错误，而是在真正需要用到相机（非 `test_mode`）时显式抛出 `RuntimeError`，`test_mode` 下 Optris SDK 缺失不再影响使用。
- **`ir_worker.py` 导入失败处理职责调整**：`optris_camera.py` 导入失败时不再自行打印/吞掉错误，由知道是否处于 `test_mode` 的调用方 `ir_worker.py` 决定该依赖缺失是否致命。

### 项目结构

- **移除仓库内 `device/` 目录**：嵌入式设备端前后端代码已完整迁移至独立仓库 [hepic_device](https://github.com/ZLoverty/hepic_device)，本仓库不再保留副本。

---
