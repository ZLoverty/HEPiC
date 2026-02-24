from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent.parent
sys.path.append(str(current_path))
import logging
import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFileDialog, QSlider, QLabel
)
from PySide6.QtCore import Qt
import numpy as np
import pyqtgraph as pg
from log_widget import LogWidget
from utils import data_cleaning

class DataProcessorWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Filament_velocity", units="mm/s")
        self.plot_widget.setLabel("left", "Extrusion Force", units="N")
        self.plot_widget.addLegend()
        self.open_csv_button = QPushButton("打开文件（.csv）")
        self.clean_button = QPushButton("清洗数据")
        self.export_button = QPushButton("导出结果")
        self.int_slider_label = QLabel("裁剪点数: 0")
        self.int_slider = QSlider(Qt.Orientation.Horizontal)
        self.int_slider.setRange(0, 100)
        self.int_slider.setSingleStep(1)
        self.int_slider.setValue(0)
        self.log_widget = LogWidget()
        self.control_widget = QWidget()
        self.control_widget.setMaximumWidth(400)

        layout = QHBoxLayout()
        layout.addWidget(self.control_widget)
        control_layout = QVBoxLayout()
        self.control_widget.setLayout(control_layout)
        control_layout.addWidget(self.open_csv_button)
        control_layout.addWidget(self.clean_button)
        control_layout.addWidget(self.export_button)
        control_layout.addWidget(self.int_slider)
        control_layout.addWidget(self.int_slider_label)
        control_layout.addWidget(self.log_widget)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
        
        # connect signals to slots
        self.open_csv_button.clicked.connect(self.open_csv_file)
        self.clean_button.clicked.connect(self.clean_data)
        self.int_slider.valueChanged.connect(self.on_slider_value_changed)
        self.export_button.clicked.connect(self.export_results)

        # logger
        self.logger = logging.getLogger(__name__)

        # variables 
        self.df = None
        self.csv_file_path = None
        self.cleaned_steps = None
        self.selected_integer = self.int_slider.value()
        self.stats_df = None
        
    def on_slider_value_changed(self, value: int):
        self.selected_integer = int(value)
        self.int_slider_label.setText(f"裁剪点数: {self.selected_integer}")
        self.plot_widget.clear()
        self.plot()

    def open_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a CSV file",
            "",
            "CSV Files (*.csv)"
        )

        if not file_path:
            self.log_widget.update_log("No CSV file selected.")
            return

        try:
            self.df = pd.read_csv(file_path)
            self.csv_file_path = file_path
            self.log_widget.update_log(
                f"Loaded CSV file: {file_path} (rows={len(self.df)}, columns={len(self.df.columns)})"
            )
        except Exception as exc:
            self.log_widget.update_log(f"Failed to load CSV file: {file_path}, error: {exc}")
            self.df = None
            self.csv_file_path = None

    def clean_data(self):
        if self.df is None:
            self.log_widget.update_log("No data to clean. Please load a CSV file first.")
            return
   
        self.cleaned_steps, data_clean, step_length = data_cleaning.clean_data(self.df)
        self.log_widget.update_log(f"Data cleaned.")
        self.log_widget.update_log(f"Number of steps: {len(self.cleaned_steps)}")
        self.log_widget.update_log(f"Inferred step length: {step_length}")
        self.plot()
    
    def plot(self):
        if self.df is None:
            self.log_widget.update_log("No data to plot. Please load and clean the data first.")
            return
        if self.cleaned_steps is None:
            self.log_widget.update_log("No cleaned data to plot. Please clean the data first.")
            return
        
        stats = data_cleaning.extrusion_statistics(self.cleaned_steps, clip=self.selected_integer)
        if stats.empty:
            self.log_widget.update_log("No statistics to plot after clipping.")
            self.stats_df = None
            return
        self.stats_df = stats.copy()

        self.plot_widget.clear()
        self.plot_widget.addLegend()

        # Keep references to avoid ErrorBarItem being garbage-collected.
        self._error_bars = []

        for idx, (temperature, g_temp) in enumerate(stats.groupby("temperature_C", sort=True)):
            color = pg.intColor(idx, hues=max(stats["temperature_C"].nunique(), 1))
            x = g_temp["feedrate_mms"].to_numpy(dtype=float)
            y = g_temp["extrusion_force_N_mean"].to_numpy(dtype=float)
            yerr = g_temp["extrusion_force_N_std"].fillna(0.0).to_numpy(dtype=float)

            self.plot_widget.plot(
                x,
                y,
                pen=None,
                symbol="o",
                symbolSize=10,
                symbolBrush=color,
                symbolPen=pg.mkPen(color, width=1),
                name=f"{temperature:.1f}°C",
            )

            error_item = pg.ErrorBarItem(
                x=x,
                y=y,
                top=yerr,
                bottom=yerr,
                beam=0.2,
                pen=pg.mkPen(color, width=1),
            )
            self.plot_widget.addItem(error_item)
            self._error_bars.append(error_item)

    def export_results(self):
        if self.stats_df is None or self.stats_df.empty:
            self.log_widget.update_log("No results to export. Please clean data first.")
            return

        default_name = "cleaned_stats.csv"
        if self.csv_file_path:
            source_path = Path(self.csv_file_path)
            default_name = f"{source_path.stem}_stats_clip{self.selected_integer}.csv"

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Results",
            str(Path(default_name).resolve()),
            "CSV Files (*.csv)"
        )

        if not save_path:
            self.log_widget.update_log("Export canceled.")
            return

        try:
            self.stats_df.to_csv(save_path, index=False)
            self.log_widget.update_log(f"Results exported: {save_path}")
        except Exception as exc:
            self.log_widget.update_log(f"Failed to export results: {exc}")

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    app = QApplication(sys.argv)
    widget = DataProcessorWidget()
    widget.setGeometry(900, 100, 500, 300)

    widget.show()
    sys.exit(app.exec())
