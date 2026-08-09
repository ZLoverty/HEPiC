"""
etp_ctl: A PySide6 GUI application for the Extrusion Test Platform experiment control, serial port data acquisition and visualization.
"""

import sys
import traceback
from pathlib import Path

if __name__ == "__main__" and not __package__ and "__compiled__" not in globals():
    package_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(package_dir.parent))
    __package__ = package_dir.name

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStackedWidget, QLabel, QFileDialog,
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QGraphicsOpacityEffect, QMenu, QDialog,
    QProxyStyle, QStyle, QTextBrowser, QMessageBox,
)
from PySide6.QtCore import (
    Signal, Slot, QThread, QTimer, QUrl, Qt, QPropertyAnimation, QEasingCurve, QEvent,
    QByteArray, QSize,
)
from PySide6.QtGui import QDesktopServices, QCursor, QPixmap, QIcon, QPainter, QTransform
from PySide6.QtSvg import QSvgRenderer
import pyqtgraph as pg
from collections import deque
from .communications import TCPClient, KlipperWorker, ConnectionTester
from .vision import VideoWorker, ProcessingWorker, IRWorker, VideoRecorder
from .tab_widgets import ConnectionWidget, VisionPageWidget, GcodeWidget, HomeWidget, IRPageWidget, JobSequenceWidget, DataProcessorWidget, QualityCheckWidget, SettingsDialog
from .app_config import (
    build_main_window_stylesheet,
    find_app_file,
    find_bundled_file,
    load_config as load_app_config,
)
from . import __app_name__, __version__
import asyncio
import csv
import json
import threading
import time
from qasync import asyncSlot, QEventLoop
import numpy as np
from datetime import datetime
import logging
import logging.handlers
import argparse


# TODO(user): 替换为许愿池表单的真实链接
WISHLIST_FORM_URL = "https://jfpolymers.feishu.cn/share/base/form/shrcndv6WDQz66gzih5Zh9vGu3f"


def _show_startup_error(exc):
    message = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path = Path(sys.argv[0]).resolve().parent / "startup_error.log"
    try:
        log_path.write_text(message, encoding="utf-8")
    except OSError:
        pass

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f"{message}\n\nLog: {log_path}",
            "HEPiC startup error",
            0x10,
        )
    except Exception:
        print(message, file=sys.stderr)


class _DataCollectorThread(threading.Thread):
    """Collects sensor data at a fixed interval independently of the Qt event loop."""

    def __init__(self, interval_s: float, collect_fn):
        super().__init__(daemon=True, name="DataCollectorThread")
        self._interval = interval_s
        self._collect = collect_fn
        self._stop_event = threading.Event()

    def run(self):
        next_t = time.perf_counter()
        while not self._stop_event.is_set():
            self._collect()
            next_t += self._interval
            remaining = next_t - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            else:
                next_t = time.perf_counter()  # fell behind — reset instead of catching up

    def stop(self):
        self._stop_event.set()


class _TopAlignedTabBarStyle(QProxyStyle):
    """Forces the tab bar to start flush with the top-left corner.

    The base style's SH_TabBar_Alignment hint otherwise decides this: macOS
    styles center the tabs vertically (for a West-positioned bar), while
    Windows/Fusion styles already left/top-align them. Overriding the hint
    makes the layout consistent across platforms.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_TabBar_Alignment:
            return int(Qt.AlignmentFlag.AlignLeft)
        return super().styleHint(hint, option, widget, returnData)


# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    
    sigNewData = Signal(dict) # update data plot
    sigNewStatus = Signal(dict) # update status panel
    sigProgress = Signal(float)
    sigFilePosition = Signal(int)
    sigEmergencyStop = Signal()
    sigForceLimitExceeded = Signal(float)

    def __init__(self, test_mode=False):
        super().__init__()
        self.test_mode = test_mode
        self.logger = logging.getLogger(__name__)
        self.config_file = find_app_file("config.json", Path(__file__), "__compiled__" in globals())
        self.changelog_file = find_bundled_file("CHANGELOG.md", Path(__file__), "__compiled__" in globals())
        self.wishlist_qrcode_file = find_bundled_file("assets/wishlist_qrcode.png", Path(__file__), "__compiled__" in globals())
        self.load_config()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setGeometry(0, 0, 1024, 768)
        self.setStyleSheet(
            build_main_window_stylesheet(
                self.background_color,
                self.foreground_color,
                self.secondary_background_color,
                self.secondary_foreground_color,
            )
        )
        pg.setConfigOption("background", self.background_color)
        pg.setConfigOption("foreground", self.foreground_color)

        # 1. (关键) 给主窗口设置一个唯一的对象名称
        self.setObjectName("MyMainWindow") 

        self.initUI()
        self._data_thread: _DataCollectorThread | None = None
        self._csv_lock = threading.Lock()
        self.status_timer = QTimer(self) # set status panel update frequency
        self.status_timer.timeout.connect(self.on_status_timer_tick)
        self._display_data_timer = QTimer(self) # UI plot refresh, decoupled from data rate
        self._display_data_timer.timeout.connect(self._emit_display_data)

        self.time_delay = 1 / self.data_frequency
        self.display_frequency = min(self.data_frequency, 15)

        self.time_delay_status = 1 / self.status_frequency
        self.hikcam_ok = False
        self.init_data()
        
        self._csv_file = None
        self._csv_writer = None
        self.worker = None
        self.klipper_worker = None
        self.video_worker = None
        self.ir_worker = None
        self.video_thread = None
        self.ir_thread = None

        self.is_recording = False
        self.record_timelapse = True
        self.IR_WORKER_OK = False

        self._force_over_limit_streak = 0
        self._safety_stop_latched = False
        self._force_safety_lock = threading.Lock()
        self.sigForceLimitExceeded.connect(self.on_force_limit_exceeded)

        self.frame_size = (512, 512)
    
    def load_config(self):
        self.config = load_app_config(self.config_file)
        self.logger.debug(f"Loaded config: {self.config}")

        # set config values
        self.data_frequency = self.config.get("data_frequency", 10)
        self.status_frequency = self.config.get("status_frequency", 5)
        self.host = self.config.get("hepic_host", "192.168.0.81")
        self.port = self.config.get("hepic_port", 10001)

        # self.test_mode = self.config.get("test_mode", False)
        self.tmp_data_maxlen = self.config.get("tmp_data_maxlen", 100)
        self.final_data_maxlen = self.config.get("final_data_maxlen", 1000000)
        self.klipper_query_delay = self.config.get("klipper_query_delay", 0.1)
        self.plot_time_window_s = self.config.get("plot_time_window_s", 60)

        # 挤出力硬性安全上限：连续 N 个采样点超过该值即触发安全急停。
        # 与质检模块的材料 force_range（软性、仅提示波动过大）是两回事，不要混用。
        # setdefault（而非单纯 .get）确保即便是升级前缺少这两个键的旧 config.json，
        # 这两项设置也会出现在"设置"对话框里，而不是被悄悄跳过。
        missing_defaults = "force_safety_limit_N" not in self.config or "force_safety_debounce_samples" not in self.config
        self.config.setdefault("force_safety_limit_N", 65.0)
        self.config.setdefault("force_safety_debounce_samples", 10)
        self.force_safety_limit_N = self.config["force_safety_limit_N"]
        self.force_safety_debounce_samples = self.config["force_safety_debounce_samples"]

        # 打包安装版读的是 ~/.HEPiC/config.json，仅首次安装时从安装包里拷贝，
        # 之后升级不会再刷新；因此这里把新补的默认值写回该文件，
        # 让老版本升级上来的用户配置也能"自愈"补全新增的键，而不是只在内存里生效一次。
        if missing_defaults:
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except OSError as exc:
                self.logger.error(f"Failed to persist force safety defaults to config: {exc}")

        # color scheme
        self.background_color = self.config.get("background_color", "black")
        self.foreground_color = self.config.get("foreground_color", "white")
        self.secondary_background_color = self.config.get("secondary_background", "#435663")
        self.secondary_foreground_color = self.config.get("secondary_foreground_color", "#A3B087")

        self.save_directory = Path(self.config.get("save_directory", "~/Desktop")).expanduser()

    def initUI(self):
        # --- 创建控件 ---
        # 标签栏
        
        self.stacked_widget = QStackedWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序
        # 强制标签栏从左上角开始排列，不受操作系统默认对齐方式影响（如 macOS 默认居中）
        self._tab_bar_style = _TopAlignedTabBarStyle(self.tabs.tabBar().style())
        self.tabs.tabBar().setStyle(self._tab_bar_style)
        # 标签页们
        self.connection_widget = ConnectionWidget(host=self.host)  
        self.home_widget = HomeWidget(time_window_s=self.plot_time_window_s)
        self.vision_page_widget = VisionPageWidget()
        self.status_widget = self.home_widget.status_widget
        self.ir_page_widget = IRPageWidget()
        self.job_sequence_widget = JobSequenceWidget()
        self.data_processor_widget = DataProcessorWidget()
        self.quality_check_widget = QualityCheckWidget()

        # 添加标签页到标签栏（图标 + hover tooltip，取代原来的文字标签）
        self.stacked_widget.addWidget(self.connection_widget)
        self.stacked_widget.addWidget(self.tabs)
        self.tabs.setIconSize(QSize(28, 28))
        tab_specs = [
            (self.home_widget, "主页.svg", "主页"),
            (self.vision_page_widget, "视频.svg", "视觉"),
            (self.ir_page_widget, "红外.svg", "红外"),
            (self.job_sequence_widget, "动作序列.svg", "G-code"),
            (self.data_processor_widget, "数据处理.svg", "数据处理"),
            (self.quality_check_widget, "质检模式.svg", "质检模式"),
        ]
        for widget, icon_file, tooltip in tab_specs:
            index = self.tabs.addTab(widget, self._load_tab_icon(icon_file, rotate=90), "")
            self.tabs.setTabToolTip(index, tooltip)
        self.tabs.setTabVisible(self.tabs.indexOf(self.vision_page_widget), False)
        self.tabs.setTabVisible(self.tabs.indexOf(self.ir_page_widget), False)
        self.setCentralWidget(self.stacked_widget)
        self._init_settings_button()

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")
        self._init_material_db_status_label()
        self._init_save_banner()

        # --- 连接信号与槽 ---
        self.connection_widget.host.connect(self.update_host_and_connect)
        self.sigNewData.connect(self.home_widget.data_widget.update_display)
        self.sigNewData.connect(self.quality_check_widget.update_sensor_data)
        self.sigNewStatus.connect(self.quality_check_widget.update_klipper_status)
        self.quality_check_widget.quality_check_gcode_requested.connect(self.on_quality_check_gcode_requested)
        self.home_widget.play_pause_button.toggled.connect(self.on_toggle_play_pause)
        self.home_widget.stop_button.clicked.connect(self.on_stop_clicked)
        self.sigNewStatus.connect(self.status_widget.update_display)
        self.sigFilePosition.connect(self.job_sequence_widget.gcode_widget.update_file_position)
        self.job_sequence_widget.gcode_widget.sigFilePath.connect(lambda _: self.tabs.setCurrentIndex(0))
        
        # --- 质检模式的材料属性会在第一次显示时自动初始化 ---

    def _init_material_db_status_label(self):
        """Show the loaded material database's data version in the status bar for quick troubleshooting."""
        try:
            from .database import get_material_database

            version = get_material_database().get_version()
        except Exception as exc:
            self.logger.error(f"Failed to read material database version: {exc}")
            version = "unknown"

        self.material_db_label = QLabel(f"材料库 v{version}")
        self.statusBar().addPermanentWidget(self.material_db_label)

    def _init_save_banner(self):
        """Transient top banner announcing the default save path each time recording starts.

        Auto-dismisses after a few seconds so it never becomes a permanent
        fixture, but still gives new users a chance to see (and change) the
        default path without a blocking dialog on every recording.
        """
        # A single widget carrying the opacity effect for the fade animation.
        # Qt's nested-QGraphicsEffect rendering (e.g. a drop shadow on a child
        # of a widget that itself has an opacity effect) is unreliable and
        # spams "Painter not active" warnings, so this deliberately avoids a
        # second effect — a border stands in for the shadow's elevation cue.
        self._save_banner = QWidget(self)
        self._save_banner.setObjectName("saveBanner")

        # Light banner on the app's dark theme, so it pops instead of blending in.
        banner_bg = self.foreground_color
        banner_text = self.background_color
        action_hover = self.secondary_foreground_color
        self._save_banner.setStyleSheet(
            f"""
            QWidget#saveBanner {{
                background-color: {banner_bg};
                border: 1px solid {self.secondary_foreground_color};
                border-radius: 10px;
            }}
            QLabel#saveBannerText {{
                color: {banner_text};
                font-size: 12pt;
                font-weight: 500;
                background: transparent;
            }}
            QPushButton#saveBannerAction {{
                background-color: {banner_text};
                color: {banner_bg};
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11pt;
                font-weight: 600;
            }}
            QPushButton#saveBannerAction:hover {{
                background-color: {action_hover};
                color: {banner_text};
            }}
            QPushButton#saveBannerClose {{
                background: transparent;
                color: {banner_text};
                border: none;
                font-size: 15pt;
                font-weight: bold;
                padding: 0px 6px;
            }}
            QPushButton#saveBannerClose:hover {{
                color: {self.secondary_background_color};
            }}
            """
        )
        layout = QHBoxLayout(self._save_banner)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(10)

        self._save_banner_label = QLabel()
        self._save_banner_label.setObjectName("saveBannerText")
        layout.addWidget(self._save_banner_label)
        layout.addStretch()

        open_btn = QPushButton("打开文件夹")
        open_btn.setObjectName("saveBannerAction")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.save_directory)))
        )
        layout.addWidget(open_btn)

        change_btn = QPushButton("修改路径")
        change_btn.setObjectName("saveBannerAction")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.clicked.connect(self._choose_save_directory)
        layout.addWidget(change_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("saveBannerClose")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._hide_save_banner)
        layout.addWidget(close_btn)

        self._save_banner_opacity = QGraphicsOpacityEffect(self._save_banner)
        self._save_banner_opacity.setOpacity(1.0)
        self._save_banner.setGraphicsEffect(self._save_banner_opacity)
        self._save_banner_fade_anim = QPropertyAnimation(self._save_banner_opacity, b"opacity", self)
        self._save_banner_fade_anim.setDuration(300)
        self._save_banner_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._save_banner_fade_anim.finished.connect(self._on_save_banner_fade_out_finished)

        self._save_banner.hide()
        self._save_banner_hide_delay_ms = 5000
        self._save_banner_timer = QTimer(self)
        self._save_banner_timer.setSingleShot(True)
        self._save_banner_timer.timeout.connect(self._start_save_banner_fade_out)

        # Polling the cursor position (rather than relying on Enter/Leave
        # events) sidesteps Qt delivering Leave to the banner whenever the
        # cursor moves onto one of its own buttons.
        self._save_banner_hover_timer = QTimer(self)
        self._save_banner_hover_timer.setInterval(150)
        self._save_banner_hover_timer.timeout.connect(self._check_save_banner_hover)

    def _show_save_banner(self):
        self._save_banner_fade_anim.stop()
        self._save_banner_opacity.setOpacity(1.0)
        self._save_banner_label.setText(f"默认保存路径：{self.save_directory}")
        self._position_save_banner()
        self._save_banner.show()
        self._save_banner.raise_()
        self._save_banner_timer.start(self._save_banner_hide_delay_ms)
        self._save_banner_hover_timer.start()

    def _start_save_banner_fade_out(self):
        self._save_banner_hover_timer.stop()
        self._save_banner_fade_anim.stop()
        self._save_banner_fade_anim.setStartValue(self._save_banner_opacity.opacity())
        self._save_banner_fade_anim.setEndValue(0.0)
        self._save_banner_fade_anim.start()

    def _on_save_banner_fade_out_finished(self):
        if self._save_banner_opacity.opacity() <= 0.0:
            self._save_banner.hide()

    def _hide_save_banner(self):
        """Dismiss immediately (used for the manual close button)."""
        self._save_banner_timer.stop()
        self._save_banner_hover_timer.stop()
        self._save_banner_fade_anim.stop()
        self._save_banner.hide()

    def _check_save_banner_hover(self):
        local_pos = self._save_banner.mapFromGlobal(QCursor.pos())
        hovering = self._save_banner.rect().contains(local_pos)
        if hovering:
            self._save_banner_timer.stop()
        elif not self._save_banner_timer.isActive():
            self._save_banner_timer.start(self._save_banner_hide_delay_ms)

    def _position_save_banner(self):
        self._save_banner.adjustSize()
        x = (self.width() - self._save_banner.width()) // 2
        self._save_banner.move(max(x, 0), 12)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_save_banner") and self._save_banner.isVisible():
            self._position_save_banner()

    def _choose_save_directory(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "选择默认保存路径", str(self.save_directory)
        )
        if not chosen:
            return
        self.save_directory = Path(chosen)
        self.config["save_directory"] = str(self.save_directory)
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except OSError as exc:
            self.logger.error(f"Failed to persist save_directory to config: {exc}")
        self.statusBar().showMessage(f"默认保存路径已更改为：{self.save_directory}")
        if self._save_banner.isVisible():
            self._show_save_banner()

    def _load_tab_icon(self, filename: str, size: int = 128, rotate: int = 0) -> QIcon:
        """Render an assets/tab_icons/*.svg (stroke="currentColor") into a QIcon.

        Qt's SVG renderer doesn't resolve currentColor the way a browser does
        (no CSS cascade to inherit from), so the substitution happens on the
        raw markup before rendering — recolored to match the tab bar's
        foreground color so it stays legible across themes. Rendering at a
        fixed high resolution rather than the on-screen icon size lets Qt
        downscale-smooth it for HiDPI displays instead of upscaling a blurry
        small pixmap. The pixmap background is left transparent (no fill),
        so it blends into whatever the tab/button background is.

        `rotate` (degrees, clockwise) counters QTabBar's own rotation: once a
        stylesheet is applied to QTabBar::tab, Qt draws a West-position tab's
        whole label — icon included — rotated so text reads bottom-to-top.
        Baking in a +90 rotation here cancels that out so the icon still
        reads left-to-right. Only tab icons need this; plain QPushButton
        icons (e.g. the settings gear) are never affected, so they pass 0.
        """
        svg_path = find_bundled_file(
            f"assets/tab_icons/{filename}", Path(__file__), "__compiled__" in globals()
        )
        svg_text = svg_path.read_text(encoding="utf-8").replace("currentColor", self.foreground_color)
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        if rotate:
            pixmap = pixmap.transformed(QTransform().rotate(rotate), Qt.TransformationMode.SmoothTransformation)
        return QIcon(pixmap)

    def _init_settings_button(self):
        """Gear icon pinned to the bottom of the vertical tab bar column, flush with the tabs above it."""
        self.settings_button = QPushButton(self.tabs)
        self.settings_button.setIcon(self._load_tab_icon("设置.svg"))
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("设置")
        self.settings_button.setFlat(True)
        self._style_settings_button()
        self.settings_button.clicked.connect(self._open_settings_menu)

        # Small red dot overlaid on the gear icon when a changelog hasn't been seen yet.
        self.settings_update_dot = QLabel("", self.tabs)
        self.settings_update_dot.setStyleSheet(
            "background-color: #e74c3c; border-radius: 5px;"
        )
        self.settings_update_dot.setFixedSize(10, 10)
        self.settings_update_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_changelog_badge()

        self.tabs.installEventFilter(self)
        QTimer.singleShot(0, self._position_settings_button)

    def _style_settings_button(self):
        self.settings_button.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: #88888855;
            }
            """
        )

    def eventFilter(self, obj, event):
        if obj is self.tabs and event.type() == QEvent.Type.Resize:
            self._position_settings_button()
        return super().eventFilter(obj, event)

    def _position_settings_button(self):
        # tabBar().width() includes reserved layout space beyond what's actually
        # drawn for a West-oriented bar; the first tab's rect is the true visible
        # column width, so the square button matches the tabs above it.
        side = self.tabs.tabBar().tabRect(0).width()
        if side <= 0:
            return
        self.settings_button.setFixedSize(side, side)
        icon_side = max(int(side * 0.6), 10)
        self.settings_button.setIconSize(QSize(icon_side, icon_side))
        y = max(self.tabs.height() - side, 0)
        self.settings_button.move(0, y)
        self.settings_button.raise_()

        dot_size = self.settings_update_dot.width()
        self.settings_update_dot.move(side - dot_size, y)
        self.settings_update_dot.raise_()

    def _update_changelog_badge(self):
        """Show the red dot iff the changelog for the running version hasn't been opened yet."""
        has_update = self.config.get("last_seen_changelog_version") != __version__
        self.settings_update_dot.setVisible(has_update)

    @Slot()
    def _open_settings_menu(self):
        menu = QMenu(self)
        settings_action = menu.addAction("设置")
        settings_action.triggered.connect(self._open_settings_dialog)

        save_video_action = menu.addAction("保存视频")
        save_video_action.setCheckable(True)
        save_video_action.setChecked(self.record_timelapse)
        save_video_action.toggled.connect(self._on_toggle_record_timelapse)

        menu.addSeparator()
        wishlist_action = menu.addAction("许愿池")
        wishlist_action.triggered.connect(self._open_wishlist_dialog)

        menu.addSeparator()
        # A drawn QIcon dot gets silently dropped by macOS's native menu rendering,
        # so the "new" marker here is a small plain-text glyph instead.
        changelog_text = "更新日志  ●" if self.settings_update_dot.isVisible() else "更新日志"
        changelog_action = menu.addAction(changelog_text)
        changelog_action.triggered.connect(self._open_changelog_dialog)

        menu.exec(self.settings_button.mapToGlobal(self.settings_button.rect().topRight()))

    @Slot()
    def _open_wishlist_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("许愿池")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        intro_label = QLabel("扫描二维码或点击下方链接，填写你的许愿/反馈：", dialog)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        qr_label = QLabel(dialog)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(self.wishlist_qrcode_file))
        if pixmap.isNull():
            qr_label.setText(f"（二维码图片未找到，请放置于：\n{self.wishlist_qrcode_file}）")
            qr_label.setWordWrap(True)
        else:
            # Scale at the screen's actual device-pixel-ratio and tag the pixmap with it,
            # otherwise it renders soft on Retina/HiDPI displays regardless of source resolution.
            target_size = 600
            dpr = self.devicePixelRatioF()
            scaled = pixmap.scaled(
                int(target_size * dpr), int(target_size * dpr),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            qr_label.setPixmap(scaled)
        layout.addWidget(qr_label)

        link_label = QLabel(f'<a href="{WISHLIST_FORM_URL}">{WISHLIST_FORM_URL}</a>', dialog)
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_label.setOpenExternalLinks(True)
        link_label.setWordWrap(True)
        layout.addWidget(link_label)

        close_button = QPushButton("关闭", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    @Slot()
    def _open_changelog_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"更新日志 - {__app_name__} v{__version__}")
        dialog.resize(480, 520)
        layout = QVBoxLayout(dialog)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        try:
            text = self.changelog_file.read_text(encoding="utf-8")
        except OSError as exc:
            self.logger.error(f"Failed to read changelog: {exc}")
            text = "暂无更新日志。"
        browser.setMarkdown(text)
        layout.addWidget(browser)

        close_button = QPushButton("关闭", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

        if self.config.get("last_seen_changelog_version") != __version__:
            self.config["last_seen_changelog_version"] = __version__
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except OSError as exc:
                self.logger.error(f"Failed to persist last_seen_changelog_version: {exc}")
            self._update_changelog_badge()

    @Slot(bool)
    def _on_toggle_record_timelapse(self, checked):
        self.record_timelapse = checked

    @Slot()
    def _open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.config.update(dialog.get_values())
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except OSError as exc:
            self.logger.error(f"Failed to persist settings to config: {exc}")
            return

        self.load_config()
        self.setStyleSheet(
            build_main_window_stylesheet(
                self.background_color,
                self.foreground_color,
                self.secondary_background_color,
                self.secondary_foreground_color,
            )
        )
        pg.setConfigOption("background", self.background_color)
        pg.setConfigOption("foreground", self.foreground_color)
        self._style_settings_button()
        self._position_settings_button()
        self.statusBar().showMessage("设置已保存，部分设置需重启后生效")

    def init_data(self):
        """Initiate a few temperary queues for the data. This will be the pool for the final data: at each tick of the timer, one number will be taken out of the pool, forming a row of a spread sheet and saved."""
        self._session_start = time.monotonic()
        existing_sensor_items = list(getattr(self, "sensor_data_items", []))
        self.base_data_items = [
            "time_s",
            "temperature_C",
            "feedrate_mms",
            "measured_temperature_C",
            "measured_feedrate_mms",
        ]
        self.sensor_data_items = existing_sensor_items
        items = list(self.base_data_items) + list(self.sensor_data_items)
        self.data = {}
        self.data_status = {} # only stores current status of the platform

        for item in items:
            self.data[item] = deque(maxlen=self.config.get("final_data_maxlen", 1000000))
            self.data_status[item] = np.nan
        if hasattr(self, "home_widget"):
            self.home_widget.data_widget.set_sensor_items(self.sensor_data_items)

    def _ensure_data_keys(self, items):
        for item in items:
            if item not in self.data:
                self.data[item] = deque(maxlen=self.final_data_maxlen)
            if item not in self.data_status:
                self.data_status[item] = np.nan

    def _register_sensor_items(self, items, sensor_labels: dict | None = None):
        added = False
        for item in items:
            if item and item not in self.sensor_data_items:
                self.sensor_data_items.append(item)
                added = True
        if added:
            self._ensure_data_keys(self.sensor_data_items)
            self.home_widget.data_widget.set_sensor_items(self.sensor_data_items, sensor_labels)

    @Slot(list)
    def on_sensor_config_received(self, sensor_columns):
        sensor_items = [col for col in sensor_columns if col not in self.base_data_items]
        zeroable_sensor_names = self.worker.get_zeroable_sensor_names() if self.worker else []
        sensor_labels = self.worker.get_sensor_labels() if self.worker else {}
        self._register_sensor_items(sensor_items, sensor_labels)
        self.status_widget.configure_tcp_sensors(sensor_items, zeroable_sensor_names, sensor_labels)
        self.logger.info(f"Configured sensor recording columns: {sensor_columns}")
        self.logger.info(f"Zeroable sensors: {zeroable_sensor_names}")

    @Slot(int)
    def show_UI(self, UI_index):
        """Show main UI"""
        self.stacked_widget.setCurrentIndex(UI_index)

    @asyncSlot()
    async def connection_test(self):
        # 树莓派服务器的 IP 地址和端口
        # IP 地址随时可能变化，所以以后应加一块屏幕方便随时读取
        # 数据端口暂定 10001

        # 1. 创建异步 Worker 实例
        self.connection_tester = ConnectionTester(self.host, self.port, test_mode=self.test_mode)

        # 2. 连接信号和槽
        self.connection_tester.test_msg.connect(self.connection_widget.update_self_test)
        self.connection_tester.success.connect(self.connect_to_ip)

        # 3. (推荐) 让 worker 在任务完成后自我销毁，避免内存泄漏
        self.connection_tester.success.connect(self.connection_tester.deleteLater)
        self.connection_tester.fail.connect(self.connection_tester.deleteLater)
        
        # 4. 直接调用 @asyncSlot 方法，qasync 会自动在事件循环中调度它
        await self.connection_tester.run()

    @asyncSlot()
    async def connect_to_ip(self):
        """Create connection with the klipper host:
        1. TCP connection with the data server on Raspberry Pi
        2. Websocket connection with the Klipper host (via Moonraker) on Raspberry Pi"""
        # 创建 TCP 连接以接收数据
        self.worker = TCPClient(self.host, self.port)
        
        # 连接信号槽
        self.worker.connection_status.connect(self.update_status)
        self.worker.sensor_config_received.connect(self.on_sensor_config_received)
        self.status_widget.zero_sensor.connect(self.worker.zero_sensor)
        
        # 创建 klipper worker（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(self.host, klipper_port, query_delay=self.klipper_query_delay, test_mode=self.test_mode)
        # 连接信号槽
        self.klipper_worker.connection_status.connect(self.update_status)
        self.klipper_worker.gcode_response.connect(self.home_widget.command_widget.display_message)
        self.klipper_worker.gcode_response.connect(self.handle_gcode_response)
        self.status_widget.set_temperature.connect(self.klipper_worker.set_temperature)
        self.home_widget.command_widget.command.connect(self.klipper_worker.send_gcode)

        self.sigEmergencyStop.connect(self.klipper_worker.emergency_stop)
        self.quality_check_widget.quality_check_abort_requested.connect(self.klipper_worker.abort_and_recover)
        self.sigProgress.connect(self.status_widget.update_progress)
        self.job_sequence_widget.gcode_widget.sigFilePath.connect(self.klipper_worker.upload_gcode_to_klipper)
        self.job_sequence_widget.gcode_widget.sigActiveGcode.connect(self.klipper_worker.set_active_gcode)
        self.home_widget.sigExtrude.connect(self.klipper_worker.send_gcode)
        self.home_widget.sigRetract.connect(self.klipper_worker.send_gcode)
        self.home_widget.klipper_status_widget.connect_worker(self.klipper_worker)
        self.klipper_worker.sigKlipperState.connect(self.quality_check_widget.update_klipper_state)
        self.klipper_worker.sigKlipperState.connect(self._on_klipper_state_for_safety_reset)

        # Let all workers run
        tcp_task = self.worker.run()
        klipper_task = self.klipper_worker.run()
        self.initiate_camera()
        self.initiate_ir_imager()

        await asyncio.gather(tcp_task, klipper_task)

    @asyncSlot(str)
    async def on_quality_check_gcode_requested(self, gcode: str):
        """Send the quality-check startup G-code through Klipper when available."""
        if not getattr(self, "klipper_worker", None):
            self.logger.warning("Quality check startup G-code requested before klipper_worker is ready")
            return
        await self.klipper_worker.send_gcode(gcode)

    @Slot(str)
    def handle_gcode_response(self, response: str):
        """Execute software-side actions embedded in G-code responses."""
        action = self._extract_software_action(response)
        if not action:
            return

        self.logger.info("Executing software action from G-code response: %s", action)

        if action == "START_RECORDING":
            self._set_recording_enabled_from_gcode(True)
        elif action == "STOP_RECORDING":
            self._set_recording_enabled_from_gcode(False)
        elif action == "START_QUALITY_CHECK":
            self._start_quality_check_extrusion_progress()
        elif action == "STOP_QUALITY_CHECK":
            self._stop_quality_check_from_gcode()
        elif action == "STATUS":
            self._set_quality_check_status_message(response)
        elif action == "ZERO_SENSORS":
            self._zero_all_sensors_from_gcode()
        else:
            self.logger.warning("Unsupported software action from G-code response: %s", action)

    def _extract_software_action(self, response: str) -> str:
        normalized = response.strip()
        for prefix in ("//", "echo:", "action:"):
            if normalized.lower().startswith(prefix.lower()):
                normalized = normalized[len(prefix):].strip()

        normalized = normalized.replace("\r", " ").replace("\n", " ").strip()
        if not normalized:
            return ""

        first_token = normalized.split()[0].strip().upper()
        supported_actions = {"START_RECORDING", "STOP_RECORDING", "START_QUALITY_CHECK", "STOP_QUALITY_CHECK", "STATUS", "ZERO_SENSORS"}
        return first_token if first_token in supported_actions else ""

    def _set_recording_enabled_from_gcode(self, enabled: bool):
        if not hasattr(self, "home_widget") or self.home_widget is None:
            return

        if enabled == self.is_recording and self.home_widget.play_pause_button.isChecked() == enabled:
            return

        self.home_widget.command_widget.display_message(
            f"action: {'START_RECORDING' if enabled else 'STOP_RECORDING'}"
        )
        self.home_widget.play_pause_button.setChecked(enabled)

    def _set_quality_check_status_message(self, response: str):
        if not hasattr(self, "quality_check_widget") or self.quality_check_widget is None:
            return
        normalized = response.strip()
        for prefix in ("//", "echo:", "action:"):
            if normalized.lower().startswith(prefix.lower()):
                normalized = normalized[len(prefix):].strip()
        normalized = normalized.replace("\r", " ").replace("\n", " ").strip()
        if normalized.upper().startswith("STATUS "):
            msg = normalized[7:].strip()
            self.quality_check_widget.set_status_message(msg)
            self.status_widget.set_status_text(msg)

    def _start_quality_check_extrusion_progress(self):
        if not hasattr(self, "quality_check_widget") or self.quality_check_widget is None:
            return
        if self.quality_check_widget.is_checking:
            self.quality_check_widget.start_extrusion_progress()

    def _stop_quality_check_from_gcode(self):
        if not hasattr(self, "quality_check_widget") or self.quality_check_widget is None:
            return
        if self.quality_check_widget.is_checking:
            self.quality_check_widget.on_quality_check_clicked()

    def _zero_all_sensors_from_gcode(self):
        if not self.worker:
            return
        self.home_widget.command_widget.display_message(
            f"action: {'ZERO_SENSORS'}"
        )
        for name in self.worker.get_zeroable_sensor_names():  
            self.worker.zero_sensor(name)
        self.logger.info("All zeroable sensors zeroed via G-code action.")

    def _refresh_displays(self):
        """Poll shared frame buffers and update all video display widgets."""
        if self.video_worker:
            frame = self.video_worker.get_latest_frame()
            if frame is not None:
                self.vision_page_widget.vision_widget.update_live_display(frame)
        if hasattr(self, "processing_worker") and self.processing_worker:
            proc_frame = self.processing_worker.get_latest_proc_frame()
            if proc_frame is not None:
                self.vision_page_widget.roi_vision_widget.update_live_display(proc_frame)
                self.home_widget.dieswell_widget.update_live_display(proc_frame)
        if self.ir_worker:
            ir_frame = self.ir_worker.get_latest_frame()
            if ir_frame is not None:
                self.ir_page_widget.image_widget.update_live_display(ir_frame)
            ir_roi = self.ir_worker.get_latest_roi_frame()
            if ir_roi is not None:
                self.home_widget.ir_roi_widget.update_live_display(ir_roi)

    @Slot()
    def initiate_camera(self):
        """Try to initiate the Hikrobot camera. 
        Ideally, if the camera lost connect by accident, the software should attempt reconnection a few times. This should be handled in the camera class."""
        try:
            # 创建 video worker （用于接收和处理视频信号）
            self.video_worker = VideoWorker(test_mode=self.test_mode, test_image_folder=self.config.get("test_image_folder", ""))
            self.video_thread = QThread()
            self.video_thread.setObjectName("VideoThread")
            self.video_worker.moveToThread(self.video_thread)
            self.hikcam_ok = True

            # if ROI has been changed in the UI, send it to the video worker, so that it can crop later images accordingly.
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.video_worker.set_roi)
            
            # update frame size 
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.update_frame_size)

            # allow user to set the exposure time of the camera
            self.vision_page_widget.sigExpTime.connect(self.video_worker.set_exp_time)

            

            # thread management: when the thread is started, call the run() method; when the thread is finished, call the deleteLater() method for both video_thread and video_worker.
            self.video_thread.started.connect(self.video_worker.run)
            self.video_thread.finished.connect(self.video_worker.deleteLater)
            self.video_thread.finished.connect(self.video_thread.deleteLater)

            self.video_thread.start()
            self._display_timer = QTimer(self)
            self._display_timer.timeout.connect(self._refresh_displays)
            self._display_timer.start(int(1000 / self.video_worker.fps))
            self._register_sensor_items(["die_diameter_px"])
            self.tabs.setTabVisible(self.tabs.indexOf(self.vision_page_widget), True)
            self.logger.info("熔体相机初始化成功！")

        except Exception as e:
            self.logger.error(f"初始化熔体状态相机失败: {e}")
            self.video_worker = None

        self.status_widget.set_die_diameter_visible(self.video_worker is not None)
        
        # 创建 image processing worker 用于处理图像，探测熔体直径
        self.processing_worker = ProcessingWorker()
        self.processing_worker.setObjectName("ProcessingWorker")

        if self.video_worker:

            # send cropped images to the processing worker for image analysis.
            self.video_worker.roi_frame_signal.connect(self.processing_worker.add_frame_to_queue)

            # allow user to invert the black and white to meet the image processing need in specific experiment.
            self.vision_page_widget.invert_button.toggled.connect(self.processing_worker.invert_toggle)

        # connect thread start to run method
        asyncio.create_task(self.processing_worker.run())
        


    @Slot()
    def initiate_ir_imager(self):
        """Try to initiate the IR image. If failed, the status flag should be marked False. Ideally, the software should attempt reconnection a few times if connection is lost. This should be handled in the IR imager class."""
        try: # 创建 IR image worker 处理红外成像仪图像，探测熔体出口温度   
            self.ir_worker = IRWorker()
            self.ir_thread = QThread()
            self.ir_thread.setObjectName("IRThread")
            self.ir_worker.moveToThread(self.ir_thread)

            # if user draw an ROI on the canvas, send the ROI info to the IR worker, so that in the future, the worker can crop the later frames
            self.ir_page_widget.image_widget.sigRoiChanged.connect(self.ir_worker.set_roi)

            # use a thread to handle the image reading and showing loop
            self.ir_thread.started.connect(self.ir_worker.run)
            self.ir_thread.finished.connect(self.ir_thread.deleteLater)
            self.ir_worker.sigFinished.connect(self.ir_worker.deleteLater)

            # the Optris Xi 400 camera comes with 6 different temperature ranges (-20~100, 0~250, 150~900). Smaller ranges, intuitively, have better precision, while larger ranges do not. Here, we read out all the available temperature range options and put them in a drop down menu for users to select.
            for item in self.ir_worker.ranges:
                self.ir_page_widget.mode_menu.addItem(f"{item["min_temp"]} - {item["max_temp"]}")
            
            # if a temperature range is chosen, set it to the IR worker, so that it can re-initiate a camera object with updated params. 
            self.ir_page_widget.mode_menu.currentIndexChanged.connect(self.ir_worker.set_range)

            # a scrollbar that allows focus adjustment.
            self.ir_page_widget.focus_bar.valueChanged.connect(self.ir_worker.set_position)

            self.ir_thread.start()
            self._register_sensor_items(["die_temperature_C"])
            self.tabs.setTabVisible(self.tabs.indexOf(self.ir_page_widget), True)

        except Exception as e:
            if self.test_mode:
                self.logger.info(f"由于测试模式开启，热成像仪模块被跳过")
            else:
                self.logger.warning(f"初始化热成像仪失败，热成像仪不可用: {e}")
            self.ir_worker = None

        self.status_widget.set_die_temperature_visible(self.ir_worker is not None)
            
        if not hasattr(self, "_display_timer") or self._display_timer is None:
            self._display_timer = QTimer(self)
            self._display_timer.timeout.connect(self._refresh_displays)
            self._display_timer.start(100)  # 10 fps display refresh
        self.show_UI(1) # show main UI anyway
        self.status_timer.start(int(self.time_delay_status * 1000))
        self._display_data_timer.start(int(1000 / self.display_frequency))
        if self._data_thread is not None:
            # Reconnecting (e.g. after a dropped connection) re-enters this method;
            # without stopping the old thread first, it keeps running orphaned in
            # the background, so two threads end up racing _check_force_safety_limit().
            self._data_thread.stop()
            self._data_thread.join(timeout=1.0)
        self._data_thread = _DataCollectorThread(self.time_delay, self._collect_data)
        self._data_thread.start()

    @Slot(bool)
    def on_toggle_play_pause(self, checked):
        if checked: 
            self.home_widget.play_pause_button.setIcon(self.home_widget.pause_icon)
            self.autosave_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.autosave_filename = self.save_directory / f"{self.autosave_prefix}_autosave.csv"

            self.logger.info("开始记录数据 ...")
            self.statusBar().showMessage(f"文件路径：{self.autosave_filename}")
            self._show_save_banner()
            with self._csv_lock:
                self._csv_columns = list(self.data_status.keys())
                self._csv_file = open(self.autosave_filename, "w", newline="", encoding="utf-8")
                self._csv_writer = csv.writer(self._csv_file)
                self._csv_writer.writerow(self._csv_columns)
            self.is_recording = True
            if self.record_timelapse and self.video_worker:
                # init video recorder
                self.autosave_video_filename = self.save_directory / f"{self.autosave_prefix}_video.mkv"
                self.video_recorder_thread = VideoRecorder(self.autosave_video_filename, *self.frame_size, fps=self.video_worker.get_fps())
                self.processing_worker.proc_frame_signal.connect(self.video_recorder_thread.add_frame)
                self.video_recorder_thread.start()
                # disable mouse in vision page
                self.vision_page_widget.vision_widget.set_mode("view")
                
        else:
            self.home_widget.play_pause_button.setIcon(self.home_widget.play_icon)
            self.logger.info("停止记录数据 ...")
            self.statusBar().showMessage("记录已停止")
            self.autosave_filename = None
            self.is_recording = False
            with self._csv_lock:
                if self._csv_file:
                    self._csv_file.close()
                    self._csv_file = None
                    self._csv_writer = None
            if self.record_timelapse and self.video_worker:
                self.processing_worker.proc_frame_signal.disconnect(self.video_recorder_thread.add_frame)
                self.video_recorder_thread.close()
                self.video_recorder_thread.sigClose.emit()
                # self.video_recorder_thread.deleteLater()
                # enable mouse after recording
                self.vision_page_widget.vision_widget.set_mode("roi")

    @Slot(str)
    def update_status(self, status):
        """更新状态栏信息"""
        self.statusBar().showMessage(status)
    
    def _collect_data(self):
        """Called from _DataCollectorThread at the configured data_frequency."""
        self.grab_status()
        self._check_force_safety_limit()
        for item in self.data:
            self.data[item].append(self.data_status[item])

        if self.is_recording:
            with self._csv_lock:
                if self._csv_writer is not None:
                    self._csv_writer.writerow([self.data_status[col] for col in self._csv_columns])

    @Slot()
    def _emit_display_data(self):
        self.sigNewData.emit(self.data)

    def on_status_timer_tick(self):
        """Update the status panel."""
        self.sigNewStatus.emit(self.data_status)
        self.sigProgress.emit(self.klipper_worker.progress)
        self.sigFilePosition.emit(self.klipper_worker.file_position)

    def grab_status(self):
        latest_sensor = dict(self.worker.latest_sensor_data) if self.worker else {}
        if "die_temperature_C" in self.sensor_data_items and self.ir_worker:
            latest_sensor["die_temperature_C"] = self.ir_worker.die_temperature
        if "die_diameter_px" in self.sensor_data_items and self.processing_worker:
            latest_sensor["die_diameter_px"] = self.processing_worker.die_diameter

        for item in self.data_status:
            # NOTE: here we append new data to both data_tmp and data. The idea is to grow both data together, so that in the preview panel we can use data to see the temporal evolution of the numbers at any time, mean time having a good file writing frequency (using the cached data_tmp) file, so that I/O is not a bottleneck.
            if item in self.sensor_data_items:
                self.data_status[item] = latest_sensor.get(item, np.nan)
            elif item == "measured_temperature_C":
                self.data_status[item] = self.klipper_worker.hotend_temperature
            elif item == "temperature_C":
                self.data_status[item] = self.klipper_worker.target_hotend_temperature
            elif item == "feedrate_mms":
                self.data_status[item] = self.klipper_worker.active_feedrate_mms
            elif item == "measured_feedrate_mms":
                self.data_status[item] = latest_sensor.get("measured_feedrate_mms", np.nan)
            elif item == "time_s":
                self.data_status[item] = time.monotonic() - self._session_start
            elif item == "gcode":
                if self.klipper_worker:
                    self.data_status[item] = self.klipper_worker.active_gcode
            else:
                self.data_status[item] = np.nan

    @asyncSlot(str)
    async def update_host_and_connect(self, host):
        self.host = host
        await self.connection_test()

    @Slot(tuple)
    def update_frame_size(self, roi):
        self.frame_size = (roi[2], roi[3])

    @Slot()
    def on_stop_clicked(self):
        self.init_data()
        self.home_widget.play_pause_button.setChecked(False)
        self.sigEmergencyStop.emit()

    def _check_force_safety_limit(self):
        """Runs on the background data-collector thread at data_frequency.

        Requires force_safety_debounce_samples consecutive over-limit readings
        before tripping, so a single sensor glitch doesn't e-stop the machine —
        the debounce window is still far faster than a human could react.
        Latched by _safety_stop_latched so it fires once per incident instead
        of re-triggering every sample while the force stays high.
        """
        value = self.data_status.get("extrusion_force_N", np.nan)
        with self._force_safety_lock:
            if self._safety_stop_latched:
                return

            if not np.isfinite(value) or value <= self.force_safety_limit_N:
                self._force_over_limit_streak = 0
                return

            self._force_over_limit_streak += 1
            if self._force_over_limit_streak < self.force_safety_debounce_samples:
                return
            self._safety_stop_latched = True

        self.sigForceLimitExceeded.emit(value)

    @Slot(float)
    def on_force_limit_exceeded(self, value):
        """Safety trip: extrusion force stayed above the hardware safety limit
        for force_safety_debounce_samples consecutive readings."""
        self.logger.warning(
            "!!! 挤出力 %.1fN 超过安全阈值 %.1fN，触发安全急停 !!!",
            value, self.force_safety_limit_N,
        )

        if getattr(self, "quality_check_widget", None) is not None and self.quality_check_widget.is_checking:
            # Quality-check gcode has no cancel mechanism — this path also
            # restarts the firmware so Klipper comes back to "ready" on its own.
            self.quality_check_widget.on_quality_check_clicked()
        else:
            self.sigEmergencyStop.emit()

        if self.home_widget.play_pause_button.isChecked():
            self.home_widget.play_pause_button.setChecked(False)

        self._show_force_safety_dialog(value)

    def _show_force_safety_dialog(self, value):
        QMessageBox.critical(
            self,
            "安全急停",
            (
                f"检测到挤出力持续超过安全阈值（{value:.1f} N > {self.force_safety_limit_N:.1f} N），"
                "系统已自动急停并停止记录。\n\n"
                "请检查设备（喷嘴堵塞、材料异常等）后，在主页点击\"固件重启\"以恢复。"
            ),
        )

    @Slot(str, str)
    def _on_klipper_state_for_safety_reset(self, state, message):
        """Re-arm the force-limit trip once Klipper is manually restarted to ready."""
        if state == "ready":
            with self._force_safety_lock:
                self._safety_stop_latched = False
                self._force_over_limit_streak = 0

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
            self.worker.deleteLater()
        if self.klipper_worker:
            self.klipper_worker.stop()
            self.klipper_worker.deleteLater()
        if self._data_thread is not None:
            self._data_thread.stop()
            self._data_thread.join(timeout=1.0)
        if hasattr(self, "_display_timer") and self._display_timer:
            self._display_timer.stop()
        if hasattr(self, "_display_data_timer") and self._display_data_timer:
            self._display_data_timer.stop()
        if self.video_worker:
            self.video_worker.stop()
        if self.video_thread:
            self.video_thread.quit()
            if not self.video_thread.wait(500):
                self.logger.warning("Video thread did not exit cleanly, terminating.")
                self.video_thread.terminate()
                self.video_thread.wait(500)
        if self.ir_worker:
            self.ir_worker.stop()
        if self.ir_thread:
            if not self.ir_thread.wait(500):
                self.logger.warning("IR thread did not exit cleanly, terminating.")
                self.ir_thread.terminate()
                self.ir_thread.wait(500)
        if hasattr(self, "processing_worker") and self.processing_worker:
            self.processing_worker.stop()
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
        self.logger.info("正在关闭应用程序...")
        event.accept()


def start_app():
    parser = argparse.ArgumentParser(
        description="Hotend extrusion platform control software.",
        epilog="Example: python main.py -t"
    )
    parser.add_argument("-t", "--test", action="store_true", help="Enable test mode")
    args = parser.parse_args()

    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handlers = []

    # In a --windowed PyInstaller build there is no console, so sys.stdout is
    # None — a StreamHandler around it would silently drop every record.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    log_dir = Path.home() / ".HEPiC" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "hepic.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handlers.append(file_handler)

    for handler in handlers:
        handler.setFormatter(log_formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)

    ### Debug module logging ###
    # logging.getLogger("HEPiC.communications.tcp_client").setLevel(logging.DEBUG)
    # logging.getLogger("HEPiC.tab_widgets.home_widget").setLevel(logging.DEBUG)
    ############################

    # Request 1ms timer resolution on Windows so QTimer fires accurately at high frequencies.

    from .database import sync_materials
    sync_materials()

    app = QApplication(sys.argv)
    window = MainWindow(test_mode=args.test)
    window.show()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        pass

# ====================================================================
# 3. 应用程序入口
# ====================================================================
if __name__ == "__main__":
    try:
        start_app()
    except Exception as exc:
        _show_startup_error(exc)
        raise
    
