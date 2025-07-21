import os
import sys

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QProgressBar, QMessageBox, QComboBox,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSpinBox
)

from core.worker import WorkerThread
from utils.ui_helpers import SmartTooltipTableWidget


# ========== 主应用 ==========
class FileCollectorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.table = None
        self.progress_label = None
        self.progress_bar = None
        self.stop_btn = None
        self.pause_resume_btn = None
        self.start_btn = None
        self.mode_box = None
        self.browse_btn = None
        self.folder_input = None
        self.param_input = None
        self.setWindowTitle("视频帧提取器")
        self.setGeometry(300, 100, 1000, 600)

        self.settings = QSettings("MyCompany", "VideoFrameExtractor")
        self.worker = None

        self.is_paused = False

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        last_path = self.settings.value("last_folder", "")

        path_layout = QHBoxLayout()
        path_label = QLabel("📁 文件夹:")
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)
        self.folder_input.setFixedWidth(300)
        self.folder_input.setText(last_path)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.setFixedWidth(60)
        self.browse_btn.clicked.connect(self.choose_folder)

        path_layout.addStretch(1)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.folder_input)
        path_layout.addWidget(self.browse_btn)
        path_layout.addStretch(1)
        layout.addLayout(path_layout)

        mode_layout = QHBoxLayout()
        mode_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        mode_label = QLabel("🎯 提取模式:")
        self.mode_box = QComboBox()
        self.mode_box.addItems(["每N秒取1帧", "每N帧取1帧"])
        self.mode_box.setCurrentIndex(0)
        self.mode_box.setFixedWidth(200)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_box)

        param_label = QLabel("参数N:")
        self.param_input = QSpinBox()
        self.param_input.setMinimum(1)
        self.param_input.setMaximum(3600)
        self.param_input.setValue(1)
        mode_layout.addWidget(param_label)
        mode_layout.addWidget(self.param_input)
        layout.addLayout(mode_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.start_btn = QPushButton("🚀 开始提取")
        self.start_btn.setFixedWidth(120)
        self.start_btn.clicked.connect(self.start_process)

        self.pause_resume_btn = QPushButton("⏸ 暂停")
        self.pause_resume_btn.setFixedWidth(120)
        self.pause_resume_btn.setEnabled(False)
        self.pause_resume_btn.clicked.connect(self.pause_resume_process)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFixedWidth(120)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("color: red;")
        self.stop_btn.clicked.connect(self.stop_process)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_resume_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        progress_bar_layout = QHBoxLayout()
        progress_bar_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(350)
        self.progress_bar.setVisible(False)
        progress_bar_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_bar_layout)

        progress_text_layout = QHBoxLayout()
        progress_text_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.progress_label = QLabel("准备就绪")
        progress_text_layout.addWidget(self.progress_label)
        layout.addLayout(progress_text_layout)

        self.table = SmartTooltipTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["文件名", "保存路径"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.sectionDoubleClicked.connect(self.resize_column_to_contents)

        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget::item:hover {
                background-color: #e6f7ff;
            }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setMouseTracking(True)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        layout.addWidget(self.table)

        self.setLayout(layout)
        self.table.cellDoubleClicked.connect(self.open_file_from_table)
        QTimer.singleShot(0, self.auto_resize_columns)

    def resize_column_to_contents(self, logical_index):
        self.table.resizeColumnToContents(logical_index)

    def open_file_from_table(self, row):
        path_item = self.table.item(row, 1)
        if path_item:
            full_path = path_item.text()
            if os.path.exists(full_path):
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(full_path)
                    elif sys.platform.startswith("darwin"):
                        os.system(f'open "{full_path}"')
                    else:
                        os.system(f'xdg-open "{full_path}"')
                except Exception as e:
                    QMessageBox.warning(self, "打开失败", f"无法打开文件:\n{full_path}\n\n错误信息:\n{str(e)}")
            else:
                QMessageBox.warning(self, "文件不存在", f"找不到该文件:\n{full_path}")

    def choose_folder(self):
        start_dir = self.folder_input.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", start_dir)
        if folder:
            self.folder_input.setText(folder)
            self.settings.setValue("last_folder", folder)

    def start_process(self):
        folder = self.folder_input.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "错误", "请选择有效的文件夹")
            return

        self.folder_input.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("开始提取...")

        mode = self.mode_box.currentIndex()
        param = self.param_input.value()
        self.worker = WorkerThread(folder, mode, param)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.show_error)
        self.worker.itemReady.connect(self.append_table_item)

        self.worker.start()

        self.start_btn.setEnabled(False)
        self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setText("⏸ 暂停")
        self.stop_btn.setEnabled(True)
        self.is_paused = False

    def auto_resize_columns(self):
        column_count = self.table.columnCount()
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return
        col_width = viewport_width // column_count
        for col in range(column_count):
            self.table.setColumnWidth(col, col_width)

    def pause_resume_process(self):
        if not self.worker:
            return

        if self.is_paused:
            self.worker.resume()
            self.pause_resume_btn.setText("⏸ 暂停")
            self.progress_label.setText("继续提取中...")
            self.is_paused = False
        else:
            self.worker.pause()
            self.pause_resume_btn.setText("▶ 继续")
            self.progress_label.setText("已暂停...")
            self.is_paused = True

    def stop_process(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.progress_label.setText("停止中...")
            self.pause_resume_btn.setEnabled(False)
            self.folder_input.setEnabled(True)
            self.browse_btn.setEnabled(True)

    def on_worker_finished(self):
        self.start_btn.setEnabled(True)
        self.pause_resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("提取完成")
        self.is_paused = False
        self.worker = None
        self.folder_input.setEnabled(True)
        self.browse_btn.setEnabled(True)

    def append_table_item(self, item):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(item["文件名"]))
        self.table.setItem(row, 1, QTableWidgetItem(item["保存路径"]))
        self.auto_resize_columns()

    def update_progress(self, filename, index, total):
        self.progress_label.setText(f"处理: {filename} ({index}/{total})")
        self.progress_bar.setValue(int(index / total * 100))

    def show_error(self, msg):
        QMessageBox.critical(self, "错误", msg)
        self.progress_label.setText("❌ 出现错误")
