# Project Path: core/WorkerThread.py
import datetime
import os
import subprocess
import sys
import threading

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
        sys.exit(1)


# 使用 nvidia-smi 获取显卡型号
def get_nvidia_gpu_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        gpus = result.stdout.decode().strip().splitlines()
        return gpus
    except Exception:
        return []


class WorkerThread(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)
    itemReady = pyqtSignal(dict)
    frameExtracted = pyqtSignal(str, int)
    modeNotice = pyqtSignal(str)

    def __init__(self, folder, mode, param, max_threads=4, image_format="png", jpg_quality=None):
        super().__init__()
        self.folder = folder
        self.mode = mode
        self.param = param
        self.max_threads = max_threads
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
        self.current_process = None  # 保存正在运行的 subprocess

        # 自动检测 GPU
        self.gpu_models = get_nvidia_gpu_info()
        self.use_gpu = bool(self.gpu_models)

    def check_pause_and_stop(self):
        self.mutex.lock()
        while self._is_paused and self._is_running:
            self.pause_cond.wait(self.mutex)
        running = self._is_running
        self.mutex.unlock()
        if not running:
            # 停止子进程
            if self.current_process:
                try:
                    self.current_process.terminate()
                except Exception:
                    pass
            raise RuntimeError("中止处理")

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
        self.mutex.lock()
        self._is_running = False
        self.pause_cond.wakeAll()
        # 终止当前子进程
        if self.current_process:
            try:
                self.current_process.terminate()
            except Exception:
                pass
        self.mutex.unlock()

    def run(self):
        try:
            # 在任务开始时显示模式
            if self.use_gpu:
                mode_text = f"检测到 NVIDIA GPU: {', '.join(self.gpu_models)}，启用 GPU 加速"
            else:
                mode_text = "未检测到 NVIDIA 显卡，启用 CPU 模式"
            self.modeNotice.emit(mode_text)

            collected = []
            file_list = [os.path.join(dp, f) for dp, dn, filenames in os.walk(self.folder) for f in filenames]
            video_files = [f for f in file_list if os.path.splitext(f)[1].lower() in ['.mp4', '.avi', '.mov', '.mkv']]
            total = len(video_files)

            for index, path in enumerate(video_files):
                if not self._is_running:
                    break
                name = os.path.basename(path)
                root = os.path.dirname(path)
                fname, ext = os.path.splitext(name)
                ext = ext.lower()

                self.check_pause_and_stop()  # 检查 pause/stop

                info = {
                    "文件名": name,
                    "所在路径": root,
                    "类型": ext.lstrip('.'),
                    "大小(MB)": round(os.path.getsize(path) / (1024 * 1024), 2),
                    "时长": "",
                    "每秒帧数": "",
                    "截取帧数量": ""
                }

                try:
                    # 获取视频信息
                    create_no_window = 0x08000000 if sys.platform == "win32" else 0
                    probe_cmd = [FFMPEG_BIN, "-hide_banner", "-i", path, "-threads", "1"]
                    self.current_process = subprocess.Popen(
                        probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        creationflags=create_no_window, shell=False
                    )
                    out_bytes, _ = self.current_process.communicate()
                    self.current_process = None
                    self.check_pause_and_stop()

                    out_text = out_bytes.decode(errors="ignore")
                    import re
                    dur_match = re.search(r"Duration:\s(\d+):(\d+):(\d+\.\d+)", out_text)
                    if not dur_match:
                        raise ValueError("无法解析视频时长")
                    h, m, s = map(float, dur_match.groups())
                    duration = h * 3600 + m * 60 + s
                    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", out_text)
                    if not fps_match:
                        raise ValueError("无法解析视频帧率")
                    fps = float(fps_match.group(1))
                    info["时长"] = format_duration(duration)
                    info["每秒帧数"] = round(fps, 2)

                    if self.mode == 0:
                        frame_count = int(duration / self.param)
                        vf_filter = f"fps=1/{self.param}"
                    else:
                        total_frames = int(duration * fps)
                        frame_count = total_frames // self.param
                        vf_filter = f"select='not(mod(n\\,{self.param}))',setpts=N/FRAME_RATE/TB"

                    info["截取帧数量"] = frame_count

                    output_dir = os.path.join(self.output_root, fname)
                    os.makedirs(output_dir, exist_ok=True)
                    ext = self.image_format.lower()
                    output_pattern = os.path.join(output_dir, f"frame_%04d.{ext}")
                    threads = self.max_threads

                    ffmpeg_cmd = [FFMPEG_BIN, "-hide_banner", "-loglevel", "error"]
                    if self.use_gpu:
                        ffmpeg_cmd += ["-hwaccel", "cuda"]
                    ffmpeg_cmd += ["-threads", str(threads), "-i", path, "-vf", vf_filter, "-vsync", "vfr"]
                    if ext == "jpg":
                        quality = self.jpg_quality if self.jpg_quality is not None else 85
                        ffmpeg_cmd += ["-qscale:v", str(int((100 - quality) / 5 + 2))]
                    ffmpeg_cmd.append(output_pattern)

                    self.current_process = subprocess.Popen(
                        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        creationflags=create_no_window, shell=False
                    )
                    self.current_process.communicate()
                    self.current_process = None

                    self.frameExtracted.emit(name, frame_count)

                except (RuntimeError, subprocess.CalledProcessError):
                    print(f"[停止或错误] {path}")
                    continue
                except Exception as e:
                    print(f"[异常] {path}: {str(e)}")
                    info["时长"] = "读取失败"

                with self.completed_lock:
                    self.completed_count += 1
                    done = self.completed_count
                self.progress.emit(name, done, total)
                self.itemReady.emit(info)
                collected.append(info)

            self.finished.emit(collected, self.folder)

        except Exception as e:
            self.error.emit(str(e))
