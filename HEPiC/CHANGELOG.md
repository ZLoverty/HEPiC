# 更新日志

## v1.6.2

### 安全性

- **彻底修复力值超限仍会弹出两次安全急停警告窗口的问题**：v1.6.1 里的修复解决的是"断线重连后新旧两个数据采集线程同时跑 `_check_force_safety_limit()` 互相竞态"，但质检过程中触发急停时 `abort_and_recover()` 会自动执行"急停 + 固件重启"，Klipper 一回到 `ready` 状态，解锁逻辑此前是不加区分地重新武装安全锁存——如果用户还没来得及处理堵料等实际问题、挤出力依然超限，debounce 很快重新攒够次数，同一次超限就会再弹一次警告窗。现改为新增 `KlipperStatusWidget.sig_manual_firmware_restart_requested` 信号，只有用户在主页手动点击"固件重启"按钮时才标记 `_manual_recovery_pending`；安全锁存只在该标记为真且 Klipper 回到 `ready` 时才解除，质检异常触发的自动重启不再能悄悄解锁。
- **修复力值超限连续弹出多个安全急停警告窗口的问题（第一轮）**：`_check_force_safety_limit()` 对 `_safety_stop_latched`/`_force_over_limit_streak` 的读写补充 `_force_safety_lock` 互斥锁；`initiate_ir_imager()` 重新连接时若旧的 `_DataCollectorThread` 仍在运行，会先 `stop()` + `join()` 再启动新线程，避免断线重连后新旧两个采集线程同时判定同一次超限、各自触发一次警告。
- **修复打包安装版下新增的挤出力安全阈值配置未真正生效的问题**：v1.6.1 中通过 `setdefault` 为旧版 `config.json` 补全 `force_safety_limit_N`/`force_safety_debounce_samples` 两个键，但只在内存里补全，从未写回配置文件；现改为检测到缺键时立即用 `json.dump` 写回 `self.config_file`（写入失败仅记日志，不阻塞启动），确保安装版升级后这两项安全阈值真正落盘、稳定生效。

### 界面与交互

- **保存路径提示条展示时间延长**：顶部保存路径提示横幅的自动淡出延迟从 2 秒延长到 5 秒，给用户更充足的时间看清并点击"打开文件夹"/"修改路径"。
- **标签栏图标居中并修复悬浮高亮失效的问题**：新增 `_TopAlignedTabBarStyle.drawControl()` 直接接管标签的背景与图标绘制：图标改为按标签的真实矩形居中绘制，不再被 Qt 默认布局为纯图标标签预留的文字间隙挤偏；同时因为给 `QTabBar::tab` 的 QSS 一旦设置背景/盒模型属性，就会让 `QStyleSheetStyle` 接管绘制并导致这种自定义竖排标签栏下的悬浮高亮失效，现完全移除该选择器下的 QSS 规则，选中/悬浮高亮统一由 proxy style 依据 `option.state` 直接绘制；另外显式打开 `WA_Hover` 属性，避免手动 `setStyle()` 后 hover 动态伪状态探测时机错位导致高亮永远不触发。此前用于抵消标签旋转的 90° 反向旋转技巧也随之不再需要。

## v1.6.1

### 安全性

- **新增挤出力硬性安全阈值，超限自动急停**：新增 `force_safety_limit_N`（默认 65 N）与 `force_safety_debounce_samples`（默认 10 个采样点）两个配置项，在数据采集线程 `_collect_data()` 中每次采样后调用 `_check_force_safety_limit()`；`extrusion_force_N` 连续超过阈值达到 debounce 次数才触发 `sigForceLimitExceeded`，避免单次传感器毛刺误触发，但该窗口仍远快于人工反应速度。触发后若正处于质检中，会走质检的急停+固件重启流程，否则直接急停并弹窗提示；通过 `_safety_stop_latched` 锁存，避免力值持续超限时重复触发，直到 Klipper 手动重启回到 `ready` 状态才重新武装。这是与质检模块材料 `force_range`（软性、仅用于提示波动过大）完全独立的硬性上限，二者不要混用。（感谢反馈@赵聪）
- **旧版本升级后自动补全安全阈值配置**：读取 `config.json` 时对新增的两个安全阈值键使用 `setdefault`，即便是升级前没有这两项的旧配置文件，也会在启动后写回默认值并出现在设置对话框中，而不是被静默跳过。

### 质检模式

- **质检按钮仅在 Klipper 处于 ready 状态时可点击**：新增 `quality_check_widget.update_klipper_state` 接收 `KlipperWorker.sigKlipperState`，非 `ready` 状态下禁用"开始质检"按钮，避免在固件未就绪（如刚触发急停、正在重启）时误触发质检 gcode。

### 界面与交互

- **标签栏由文字标题改为图标 + 悬浮提示**：新增 `HEPiC/assets/tab_icons/*.svg` 图标集，`_load_tab_icon()` 在运行时将 SVG 中的 `currentColor` 替换为当前主题前景色后渲染为 `QIcon`，并按固定高分辨率渲染再降采样，避免 HiDPI 下模糊；West 方向的标签栏本身会把整个标签（含图标）旋转显示以让文字竖排，因此额外叠加 90° 反向旋转抵消，保证图标仍然正向显示。标签文字改为 hover tooltip 展示。设置按钮的齿轮 emoji 同步替换为 SVG 图标。
- **修改温度设置来源不再局限于本地输入框**：`platform_status_widget.py` 新增对 `temperature_C`（目标温度，而非已测量温度）的处理，只要输入框未处于聚焦状态就跟随后台状态刷新，用于同步"其他终端/其他方式修改了目标温度"时本机输入框的显示值，避免出现界面显示与实际下发目标不一致的情况。

### 资源与打包

- **合并两套图标目录，修复图标在部分打包路径下加载失败的问题**：原来 `急停`/`归零` 图标位于 `HEPiC/tab_widgets/icons/`，与新版设置菜单等功能使用的 `HEPiC/assets/icons/` 是两套并行目录；现统一迁移到 `HEPiC/assets/icons/`，`home_widget.py`、`platform_status_widget.py` 改为通过 `app_config.find_bundled_file()` 加载，行为与其他 bundled 资源一致；`release.yml`、`build_pyinstaller.bat` 中对应的 PyInstaller `--add-data` 参数一并清理，不再重复打包旧目录。
- **--windowed 打包模式下补充文件日志**：PyInstaller `--windowed` 构建没有控制台，`sys.stdout` 为 `None`，此前的 `StreamHandler(sys.stdout)` 会静默丢失所有日志；现改为按 `sys.stdout is not None` 判断是否附加控制台 handler，并始终附加一个 `RotatingFileHandler`（写入 `~/.HEPiC/logs/hepic.log`，单文件最大 5MB，保留 3 份），保证安装版也能留存日志用于排查问题。
- **新增源代码上传至腾讯云 COS 的 CI 工作流**（`.github/workflows/cos-source.yml`），用于内部分发/归档源码包。

### 修复

- **修复播放/暂停按钮切换时一闪弹出命令行窗口的问题**：`connection_tester.py` 中 ping 子进程、`video_recorder.py` 中录像子进程在 Windows 上均补充 `creationflags=subprocess.CREATE_NO_WINDOW`，避免每次触发 ping 检测或启动录像时短暂弹出控制台窗口，在 `--windowed` 打包后尤其明显。

---

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
