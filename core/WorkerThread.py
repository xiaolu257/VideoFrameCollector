# Project Path: core/WorkerThread.py
import datetime
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt6.QtWidgets import QMessageBox


def format_duration(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h}h{m}m{s}s" if h else f"{m}m{s}s"


# 获取项目内的 ffmpeg/ffprobe 路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")

FFMPEG_BIN = os.path.join(FFMPEG_DIR, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
FFPROBE_BIN = os.path.join(FFMPEG_DIR, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")


def check_ffmpeg_exists(gui_mode=True):
    """
    检查 ffmpeg 和 ffprobe 是否存在
    :param gui_mode: True 表示 GUI 弹窗模式，False 表示 CLI 打印并退出
    """
    missing = []
    if not os.path.isfile(FFMPEG_BIN):
        missing.append(FFMPEG_BIN)
    if not os.path.isfile(FFPROBE_BIN):
        missing.append(FFPROBE_BIN)

    if missing:
        msg = "缺少必要的组件：\n" + "\n".join(missing) + "\n\n请将 ffmpeg.exe 和 ffprobe.exe 放入项目的 ffmpeg/ 文件夹。"

        if gui_mode:
            QMessageBox.critical(None, "缺少 ffmpeg", msg)
        else:
            print(msg)

        sys.exit(1)  # 终止程序


class WorkerThread(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)
    itemReady = pyqtSignal(dict)
    frameExtracted = pyqtSignal(str, int)
    processing = pyqtSignal(str)

    def __init__(self, folder, mode, param, max_threads=4, image_format="png", jpg_quality=None):
        super().__init__()
        self.folder = folder
        self.mode = mode
        self.param = param
        self.max_threads = max_threads  # 存储线程数
        self.image_format = image_format
        self.jpg_quality = jpg_quality
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

                    # ---------- 调用 ffprobe ----------
                    probe_cmd = [
                        FFPROBE_BIN,
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate,duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        path
                    ]
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, check=True,
                                            creationflags=create_no_window, shell=False)
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

                    # ---------- 计算帧数量 ----------
                    if self.mode == 0:
                        frame_count = int(duration / self.param)
                    else:
                        total_frames = int(duration * fps)
                        frame_count = total_frames // self.param

                    info["截取帧数量"] = frame_count

                    # ---------- 输出目录 ----------
                    output_dir = os.path.join(self.output_root, fname)
                    os.makedirs(output_dir, exist_ok=True)

                    if self.mode == 0:
                        vf_filter = f"select='not(mod(t\\,{self.param}))',setpts=N/FRAME_RATE/TB"
                    else:
                        vf_filter = f"select='not(mod(n\\,{self.param}))',setpts=N/FRAME_RATE/TB"

                    ext = self.image_format.lower()
                    output_pattern = os.path.join(output_dir, f"frame_%04d.{ext}")
                    threads = self.max_threads

                    # ---------- 调用 ffmpeg ----------
                    if ext == "jpg":
                        quality = self.jpg_quality if self.jpg_quality is not None else 85
                        ffmpeg_cmd = [
                            FFMPEG_BIN,
                            "-hide_banner", "-loglevel", "error",
                            "-threads", str(threads),
                            "-i", path,
                            "-vf", vf_filter,
                            "-vsync", "vfr",
                            "-qscale:v", str(int((100 - quality) / 5 + 2)),
                            output_pattern
                        ]
                    else:
                        ffmpeg_cmd = [
                            FFMPEG_BIN,
                            "-hide_banner", "-loglevel", "error",
                            "-threads", str(threads),
                            "-i", path,
                            "-vf", vf_filter,
                            "-vsync", "vfr",
                            output_pattern
                        ]

                    subprocess.run(ffmpeg_cmd, check=True,
                                   creationflags=create_no_window, shell=False)

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
