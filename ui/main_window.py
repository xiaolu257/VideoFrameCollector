import datetime
import os
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QProgressBar, QMessageBox, QComboBox,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSpinBox, QTableWidget, QToolTip
)


def format_duration(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h}h{m}m{s}s" if h else f"{m}m{s}s"


class SmartTooltipTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
        self._last_tooltip_text = ""

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        if item:
            rect = self.visualItemRect(item)
            fm = QFontMetrics(item.font() if item.font() else self.font())
            text = item.text()
            text_width = fm.horizontalAdvance(text)
            cell_width = rect.width() - 6

            if text_width > cell_width:
                if self._last_tooltip_text != text:
                    item.setToolTip(text)
                    self._last_tooltip_text = text
            else:
                if self._last_tooltip_text != "":
                    item.setToolTip("")
                    self._last_tooltip_text = ""
        else:
            if self._last_tooltip_text != "":
                self._last_tooltip_text = ""
                QToolTip.hideText()
        super().mouseMoveEvent(event)


# ========== 后台线程 ==========


class WorkerThread(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)
    itemReady = pyqtSignal(dict)
    frameExtracted = pyqtSignal(str, int)
    processing = pyqtSignal(str)

    def __init__(self, folder, mode, param, max_threads=4):
        super().__init__()
        self.folder = folder
        self.mode = mode
        self.param = param
        self.max_threads = max_threads  # 存储线程数
        self._is_running = True
        self._is_paused = False
        self.mutex = QMutex()
        self.pause_cond = QWaitCondition()
        self.output_root = os.path.join(
            self.folder, "帧生成_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        os.makedirs(self.output_root, exist_ok=True)

        self.completed_count = 0
        self.completed_lock = threading.Lock()

    def check_pause_and_stop(self):
        self.mutex.lock()
        while self._is_paused and self._is_running:
            self.pause_cond.wait(self.mutex)
        running = self._is_running
        self.mutex.unlock()
        if not running:
            raise RuntimeError("中止处理")

    def run(self):
        try:
            collected = []
            file_list = [os.path.join(dp, f) for dp, dn, filenames in os.walk(self.folder) for f in filenames]
            video_files = [f for f in file_list if os.path.splitext(f)[1].lower() in ['.mp4', '.avi', '.mov', '.mkv']]
            total = len(video_files)

            def process_file(path_index):
                index, path = path_index
                name = os.path.basename(path)
                root = os.path.dirname(path)
                fname, ext = os.path.splitext(name)
                ext = ext.lower()

                try:
                    self.check_pause_and_stop()
                    self.processing.emit(name)

                    info = {
                        "文件名": name,
                        "所在路径": root,
                        "类型": ext.lstrip('.'),
                        "大小(MB)": round(os.path.getsize(path) / (1024 * 1024), 2),
                        "时长": "",
                        "每秒帧数": "",
                        "截取帧数量": ""
                    }

                    create_no_window = 0x08000000 if sys.platform == "win32" else 0
                    cmd = f'ffprobe -v error -select_streams v:0 -show_entries stream=duration,r_frame_rate -of default=noprint_wrappers=1:nokey=1 "{path}"'
                    result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, check=True, creationflags=create_no_window)
                    self.check_pause_and_stop()

                    output_lines = result.stdout.decode().splitlines()
                    if len(output_lines) < 2:
                        raise ValueError(f"ffprobe 输出异常：{output_lines}")

                    frame_rate_expr = output_lines[0]
                    duration = float(output_lines[1])

                    try:
                        fps = float(Fraction(frame_rate_expr.strip()))
                    except Exception as e:
                        raise ValueError(f"无法解析帧率 '{frame_rate_expr.strip()}': {str(e)}")

                    info["时长"] = format_duration(duration)
                    info["每秒帧数"] = round(fps, 2)

                    if self.mode == 0:
                        frame_count = int(duration / self.param)
                    else:
                        total_frames = int(duration * fps)
                        frame_count = total_frames // self.param

                    info["截取帧数量"] = frame_count

                    output_dir = os.path.join(self.output_root, fname)
                    os.makedirs(output_dir, exist_ok=True)

                    if self.mode == 0:
                        vf_filter = f"select='not(mod(t\\,{self.param}))',setpts=N/FRAME_RATE/TB"
                    else:
                        vf_filter = f"select='not(mod(n\\,{self.param}))',setpts=N/FRAME_RATE/TB"

                    output_pattern = os.path.join(output_dir, "frame_%04d.png")
                    threads = self.max_threads  # 使用用户指定的线程数
                    ffmpeg_cmd = f'ffmpeg -hide_banner -loglevel error -threads {threads} -i "{path}" -vf "{vf_filter}" -vsync vfr "{output_pattern}"'
                    subprocess.run(shlex.split(ffmpeg_cmd), check=True, creationflags=create_no_window)

                    self.frameExtracted.emit(name, frame_count)

                except (subprocess.CalledProcessError, RuntimeError) as e:
                    print(f"[停止或错误] {path}: {e}")
                    return None
                except Exception as e:
                    print(f"[异常] {path}: {str(e)}")
                    info["时长"] = "读取失败"

                with self.completed_lock:
                    self.completed_count += 1
                    done = self.completed_count

                self.progress.emit(name, done, total)
                return info

            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                futures = {executor.submit(process_file, (i, path)): path for i, path in enumerate(video_files)}
                for future in as_completed(futures):
                    if not self._is_running:
                        break  # 主线程中断：不等余下任务
                    info = future.result()
                    if info:
                        collected.append(info)
                        self.itemReady.emit(info)

            self.finished.emit(collected, self.folder)

        except Exception as e:
            self.error.emit(str(e))

    def pause(self):
        self.mutex.lock()
        self._is_paused = True
        self.mutex.unlock()

    def resume(self):
        self.mutex.lock()
        self._is_paused = False
        self.pause_cond.wakeAll()
        self.mutex.unlock()

    def stop(self):
        self._is_running = False
        self.resume()  # 唤醒挂起线程，以便它能检测停止状态退出


# ========== 主应用 ==========

class FileCollectorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.thread_input = None
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
        self.total_count = 0  # 用于记录所有待处理视频数

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

        # === 新增线程数控制行 ===
        thread_layout = QHBoxLayout()
        thread_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        thread_label = QLabel("⚙️ 最大线程数:")
        self.thread_input = QComboBox()
        cpu_threads = os.cpu_count() or 4
        for i in range(1, cpu_threads + 1):
            self.thread_input.addItem(str(i))
        default_threads = min(4, cpu_threads)
        self.thread_input.setCurrentIndex(default_threads - 1)  # 默认选择第 default_threads 项
        thread_layout.addWidget(thread_label)
        thread_layout.addWidget(self.thread_input)
        layout.addLayout(thread_layout)

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

        headers = ["文件名", "所在路径", "类型", "大小(MB)", "时长", "每秒帧数", "截取帧数量"]
        self.table = SmartTooltipTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
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

    def show_current_processing(self, filename):
        if self.worker:
            done = self.worker.completed_count
            total = self.total_count if self.total_count > 0 else done
            self.progress_label.setText(f"正在处理：{filename}（已完成 {done}/{total}）")

    def update_progress(self, filename, done, total):
        self.progress_bar.setValue(int(done / total * 100))
        # ✅ 实时更新文本：不仅在当前任务开始时更新，还要在任何任务完成时更新
        self.progress_label.setText(f"正在处理：{filename}（已完成 {done}/{total}）")

    def start_process(self):
        folder = self.folder_input.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "错误", "请选择有效的文件夹")
            return

        file_list = [os.path.join(dp, f) for dp, dn, filenames in os.walk(folder) for f in filenames]
        video_files = [f for f in file_list if os.path.splitext(f)[1].lower() in ['.mp4', '.avi', '.mov', '.mkv']]
        self.total_count = len(video_files)

        self.folder_input.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("开始提取...")

        mode = self.mode_box.currentIndex()
        param = self.param_input.value()
        thread_count = int(self.thread_input.currentText())
        self.worker = WorkerThread(folder, mode, param, max_threads=thread_count)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.show_error)
        self.worker.itemReady.connect(self.append_table_item)
        self.worker.processing.connect(self.show_current_processing)

        self.worker.start()

        self.start_btn.setEnabled(False)
        self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setText("⏸ 暂停")
        self.stop_btn.setEnabled(True)
        self.is_paused = False

    def resize_column_to_contents(self, logical_index):
        self.table.resizeColumnToContents(logical_index)

    def open_file_from_table(self, row):
        filename_item = self.table.item(row, 0)
        if not filename_item or not self.worker:
            return

        video_name = filename_item.text()
        output_dir = os.path.join(self.worker.output_root, os.path.splitext(video_name)[0])

        if os.path.exists(output_dir):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(output_dir)
                elif sys.platform.startswith("darwin"):
                    subprocess.run(["open", output_dir])
                else:
                    subprocess.run(["xdg-open", output_dir])
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{output_dir}\n\n错误信息:\n{str(e)}")
        else:
            QMessageBox.warning(self, "目录不存在", f"找不到帧图目录:\n{output_dir}")

    def choose_folder(self):
        start_dir = self.folder_input.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", start_dir)
        if folder:
            self.folder_input.setText(folder)
            self.settings.setValue("last_folder", folder)

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
        self.folder_input.setEnabled(True)
        self.browse_btn.setEnabled(True)

        output_dir = self.worker.output_root if self.worker else None
        self.worker = None

        if output_dir and os.path.exists(output_dir):
            reply = QMessageBox.question(
                self,
                "提取完成",
                f"所有帧图像已保存至:\n{output_dir}\n\n是否打开该文件夹？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(output_dir)
                    elif sys.platform.startswith("darwin"):
                        subprocess.run(["open", output_dir])
                    else:
                        subprocess.run(["xdg-open", output_dir])
                except Exception as e:
                    QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{output_dir}\n\n错误信息:\n{str(e)}")

    def append_table_item(self, item):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(item["文件名"]))
        self.table.setItem(row, 1, QTableWidgetItem(item["所在路径"]))
        self.table.setItem(row, 2, QTableWidgetItem(item["类型"]))
        self.table.setItem(row, 3, QTableWidgetItem(str(item["大小(MB)"])))
        self.table.setItem(row, 4, QTableWidgetItem(item["时长"]))
        self.table.setItem(row, 5, QTableWidgetItem(str(item["每秒帧数"])))
        self.table.setItem(row, 6, QTableWidgetItem(str(item["截取帧数量"])))
        self.auto_resize_columns()

    def show_error(self, msg):
        QMessageBox.critical(self, "错误", msg)
        self.progress_label.setText("❌ 出现错误")
