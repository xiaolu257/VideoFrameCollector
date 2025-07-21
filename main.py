import sys
import os
import hashlib
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager
from datetime import datetime
import threading

import cv2
import psutil

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QProgressBar, QComboBox,
    QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# --- 视频帧提取核心函数 ---

def is_video_file(filename):
    return filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".mpeg"))

def safe_en_path(rel_path):
    hash_str = hashlib.md5(rel_path.encode('utf-8')).hexdigest()
    ext = os.path.splitext(rel_path)[1]
    return f"{hash_str}{ext}"

def extract_frames_task(args):
    video_path, rel_path, temp_frame_folder, mode, interval, stop_event = args

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"视频文件": os.path.basename(video_path), "帧数量": 0, "保存路径": "", "原始相对路径": rel_path}

    fps = cap.get(cv2.CAP_PROP_FPS)
    if "秒" in mode and fps > 0:
        frame_interval = max(1, int(round(fps * interval)))
    else:
        frame_interval = max(1, int(interval))

    count = 0
    saved = 0
    while cap.isOpened():
        if stop_event.is_set():
            break

        ret, frame = cap.read()
        if not ret or stop_event.is_set():
            break

        if count % frame_interval == 0:
            save_path = os.path.join(temp_frame_folder, f"frame_{count:06d}.jpg")
            if cv2.imwrite(save_path, frame):
                saved += 1
        count += 1

    cap.release()

    return {
        "视频文件": os.path.basename(video_path),
        "帧数量": saved,
        "临时路径": temp_frame_folder,
        "原始相对路径": rel_path
    }

def collect_frames_batch(root_folder, output_root, mode, interval,
                         progress_callback=None, stop_flag_func=None,
                         result_callback=None, max_workers=None):
    video_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for name in filenames:
            if is_video_file(name):
                full_path = os.path.join(dirpath, name)
                rel_path = os.path.relpath(full_path, root_folder)
                video_files.append((full_path, rel_path))

    total_files = len(video_files)
    if total_files == 0:
        return

    with tempfile.TemporaryDirectory() as temp_root, Manager() as manager:
        stop_event = manager.Event()

        tasks = []
        for full_path, rel_path in video_files:
            safe_folder_name = safe_en_path(rel_path) + "_frames"
            temp_frame_folder = os.path.join(temp_root, safe_folder_name)
            os.makedirs(temp_frame_folder, exist_ok=True)
            tasks.append((full_path, rel_path, temp_frame_folder, mode, interval, stop_event))

        if max_workers is None:
            cpu_idle = 100 - psutil.cpu_percent(interval=1)
            estimated_cores = int(os.cpu_count() * (cpu_idle / 100.0))
            max_workers = max(1, min(estimated_cores, os.cpu_count() - 1))

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {executor.submit(extract_frames_task, task): task for task in tasks}

            for idx, future in enumerate(as_completed(future_to_task), start=1):
                if stop_flag_func and stop_flag_func():
                    stop_event.set()
                    break

                result = future.result()
                rel_path = result["原始相对路径"]
                temp_frame_folder = result.get("临时路径", "")
                final_save_dir = os.path.join(output_root, os.path.splitext(rel_path)[0])
                os.makedirs(final_save_dir, exist_ok=True)

                if os.path.exists(temp_frame_folder):
                    for frame_filename in os.listdir(temp_frame_folder):
                        shutil.move(
                            os.path.join(temp_frame_folder, frame_filename),
                            os.path.join(final_save_dir, frame_filename)
                        )

                result["保存路径"] = os.path.abspath(final_save_dir)
                result.pop("临时路径", None)

                if progress_callback:
                    progress_callback(idx, total_files, result["视频文件"])
                if result_callback:
                    result_callback(result)

# --- PyQt6 线程封装 ---

class FrameCollectorThread(QThread):
    progress_signal = pyqtSignal(int, int, str)  # current, total, filename
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, folder, mode, interval, max_workers):
        super().__init__()
        self.folder = folder
        self.mode = mode
        self.interval = interval
        self.max_workers = max_workers
        self._stop_flag = False

    def run(self):
        try:
            def progress_callback(current, total, filename):
                self.progress_signal.emit(current, total, filename)

            def result_callback(result):
                self.result_signal.emit(result)

            def stop_flag_func():
                return self._stop_flag

            collect_frames_batch(
                self.folder,
                os.path.join(self.folder, f"帧收集_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                self.mode, self.interval,
                progress_callback=progress_callback,
                stop_flag_func=stop_flag_func,
                result_callback=result_callback,
                max_workers=self.max_workers
            )
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        self._stop_flag = True

# --- PyQt6 主界面 ---

class FrameCollectorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频帧收集器 v1.0")
        self.resize(900, 600)

        self.layout = QVBoxLayout(self)

        # 文件夹选择
        folder_layout = QHBoxLayout()
        folder_label = QLabel("选择文件夹：")
        self.folder_edit = QLineEdit()
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(self.browse_btn)
        self.layout.addLayout(folder_layout)

        # 进度条和百分比
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_percent_label = QLabel("0%")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_percent_label)
        self.layout.addLayout(progress_layout)

        # 当前进度信息
        self.progress_info_label = QLabel("")
        self.layout.addWidget(self.progress_info_label)

        # 模式选择和间隔
        mode_layout = QHBoxLayout()
        mode_label = QLabel("提取模式：")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["每N秒提取一帧", "每N帧提取一帧"])
        self.mode_combo.setCurrentIndex(0)
        interval_label = QLabel("间隔值：")
        self.interval_edit = QLineEdit("1")
        self.interval_edit.setFixedWidth(60)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(interval_label)
        mode_layout.addWidget(self.interval_edit)
        self.layout.addLayout(mode_layout)

        # CPU信息和最大进程数选择
        proc_layout = QHBoxLayout()
        self.cpu_label = QLabel("CPU占用率：系统 0.0%")
        proc_layout.addWidget(self.cpu_label)
        proc_layout.addStretch()
        proc_layout.addWidget(QLabel("最大进程数："))
        self.max_proc_combo = QComboBox()
        cpu_count = os.cpu_count()
        for i in range(1, cpu_count + 1):
            self.max_proc_combo.addItem(str(i))
        self.max_proc_combo.setCurrentIndex(max(cpu_count // 3 - 1, 0))
        proc_layout.addWidget(self.max_proc_combo)
        self.layout.addLayout(proc_layout)

        # 开始/中断按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始处理")
        self.start_btn.setStyleSheet("background-color: green; color: white")
        self.stop_btn = QPushButton("中断处理")
        self.stop_btn.setStyleSheet("background-color: red; color: white")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        self.layout.addLayout(btn_layout)

        # 结果展示树形控件
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["视频文件", "帧数量", "保存路径"])
        self.layout.addWidget(self.tree)

        # 绑定信号槽
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.tree.itemDoubleClicked.connect(self.open_folder)

        # 启动 CPU 使用率监控线程
        self._stop_monitoring = False
        self.monitor_thread = threading.Thread(target=self.monitor_cpu_usage, daemon=True)
        self.monitor_thread.start()

        self.worker_thread = None

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.folder_edit.setText(folder)

    def monitor_cpu_usage(self):
        while not self._stop_monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                self.cpu_label.setText(f"CPU占用率：系统 {cpu_percent:.1f}%")
            except Exception:
                pass

    def start_processing(self):
        folder = self.folder_edit.text()
        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "错误", "请选择有效的文件夹路径！")
            return

        mode = self.mode_combo.currentText()

        try:
            interval = int(self.interval_edit.text())
            if interval <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.critical(self, "错误", "请输入有效的间隔值（正整数）")
            return

        max_workers = int(self.max_proc_combo.currentText())

        self.tree.clear()
        self.progress_bar.setValue(0)
        self.progress_percent_label.setText("0%")
        self.progress_info_label.setText("")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.worker_thread = FrameCollectorThread(folder, mode, interval, max_workers)
        self.worker_thread.progress_signal.connect(self.update_progress)
        self.worker_thread.result_signal.connect(self.add_tree_row)
        self.worker_thread.finished_signal.connect(self.finish_processing)
        self.worker_thread.error_signal.connect(self.handle_error)
        self.worker_thread.start()

    def stop_processing(self):
        if self.worker_thread:
            self.worker_thread.stop()
            self.progress_info_label.setText("正在请求中断，请稍候...")
            self.stop_btn.setEnabled(False)

    def update_progress(self, current, total, filename):
        progress_value = int(current * 100 / total)
        self.progress_bar.setValue(progress_value)
        self.progress_percent_label.setText(f"{progress_value}%")
        self.progress_info_label.setText(f"已完成：{filename} ({current}/{total})")

    def add_tree_row(self, result):
        item = QTreeWidgetItem([result["视频文件"], str(result["帧数量"]), result["保存路径"]])
        self.tree.addTopLevelItem(item)

    def finish_processing(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.worker_thread and self.worker_thread._stop_flag:
            self.progress_info_label.setText("处理被中断。")
            QMessageBox.information(self, "中断", "已中断处理。")
        else:
            self.progress_info_label.setText("处理完成！")
            QMessageBox.information(self, "完成", "所有帧提取完成！")

    def handle_error(self, error_msg):
        QMessageBox.critical(self, "错误", f"处理出现异常：{error_msg}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def open_folder(self, item, column):
        folder_path = item.text(2)
        if not os.path.exists(folder_path):
            QMessageBox.warning(self, "错误", "文件夹不存在")
            return
        import platform
        import subprocess
        try:
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开文件夹：{e}")

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, '确认退出',
                "任务正在进行，是否中断并退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker_thread.stop()
                self.worker_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# --- 主入口 ---

def main():
    from multiprocessing import freeze_support
    freeze_support()

    app = QApplication(sys.argv)
    window = FrameCollectorApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
