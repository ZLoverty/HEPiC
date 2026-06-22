import logging
from itertools import islice

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget
import pyqtgraph as pg


class DataPlotWidget(QWidget):
    def __init__(self, logger=None, line_width=2, time_window_s=60):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        self.time_window_s = time_window_s
        self.line_width = line_width

        self.sensor_items: list[str] = []
        self.sensor_labels: dict[str, str] = {}
        self.checkboxes: dict[str, QCheckBox] = {}
        self.plots: dict[str, pg.PlotWidget] = {}
        self.curves: dict[str, pg.PlotDataItem] = {}

        self.color_pool = [
            "#2980b9",
            "#e74c3c",
            "#27ae60",
            "#f39c12",
            "#8e44ad",
            "#16a085",
            "#2c3e50",
            "#c0392b",
            "#1abc9c",
            "#d35400",
        ]

        self.checkbox_layout = QHBoxLayout()
        self.checkbox_layout.setSpacing(12)
        self.plot_layout = QVBoxLayout()

        layout = QVBoxLayout()
        layout.addLayout(self.checkbox_layout)
        layout.addLayout(self.plot_layout)
        self.setLayout(layout)

    def _next_color(self, idx: int) -> str:
        return self.color_pool[idx % len(self.color_pool)]

    def set_sensor_items(self, sensor_items: list[str], sensor_labels: dict[str, str] | None = None):
        if sensor_labels is not None:
            self.sensor_labels = sensor_labels

        new_items = [item for item in sensor_items if item]

        # Remove disappeared sensors.
        for key in list(self.checkboxes.keys()):
            if key not in new_items:
                self._remove_plot(key)
                checkbox = self.checkboxes.pop(key)
                self.checkbox_layout.removeWidget(checkbox)
                checkbox.deleteLater()

        # Add new sensors.
        for key in new_items:
            if key in self.checkboxes:
                continue
            display_name = self.sensor_labels.get(key, key)
            checkbox = QCheckBox(display_name)
            checkbox.toggled.connect(lambda checked, name=key: self._on_toggle_sensor(name, checked))
            checkbox.setChecked(True)
            self.checkboxes[key] = checkbox
            self.checkbox_layout.addWidget(checkbox)

        self.sensor_items = new_items

    def _on_toggle_sensor(self, sensor_name: str, checked: bool):
        if checked:
            self._add_plot(sensor_name)
        else:
            self._remove_plot(sensor_name)

    def _add_plot(self, sensor_name: str):
        if sensor_name in self.plots:
            return
        color = self._next_color(len(self.plots))
        display_name = self.sensor_labels.get(sensor_name, sensor_name)
        plot = pg.PlotWidget(title=display_name)
        curve = plot.plot(pen=pg.mkPen(color, width=self.line_width))
        self.plots[sensor_name] = plot
        self.curves[sensor_name] = curve
        self.plot_layout.addWidget(plot)

    def _remove_plot(self, sensor_name: str):
        plot = self.plots.pop(sensor_name, None)
        self.curves.pop(sensor_name, None)
        if plot is not None:
            self.plot_layout.removeWidget(plot)
            plot.deleteLater()

    @staticmethod
    def _tail(seq, n: int) -> list:
        """Return the last n items of seq in O(n) without copying the full sequence."""
        return list(islice(reversed(seq), n))[::-1]

    @Slot(dict)
    def update_display(self, data: dict):
        try:
            time_deque = data.get("time_s")
            if not time_deque:
                return

            latest_time = time_deque[-1]
            cutoff = latest_time - self.time_window_s

            # Count points within the time window by walking backwards (O(n_shown))
            n = 0
            for t in reversed(time_deque):
                if t < cutoff:
                    break
                n += 1
            if n == 0:
                return

            x_data = self._tail(time_deque, n)

            for sensor_name, curve in self.curves.items():
                y_deque = data.get(sensor_name)
                if not y_deque:
                    continue
                y_data = self._tail(y_deque, n)
                n_pts = min(len(x_data), len(y_data))
                if n_pts <= 0:
                    continue
                curve.setData(x_data[:n_pts], y_data[:n_pts])
        except Exception as e:
            self.logger.error(f"data_plot_widget update error: {e}")
