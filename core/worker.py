# Project Path: core/worker.py
import os
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition


def format_duration(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h}h{m}m{s}s" if h else f"{m}m{s}s"


# ========== 后台线程 ==========

class WorkerThread(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)
    itemReady = pyqtSignal(dict)

    def __init__(self, folder, mode):
        super().__init__()
        self.folder = folder
        self.mode = mode
        self._is_running = True
        self._is_paused = False
        self.mutex = QMutex()
        self.pause_cond = QWaitCondition()

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

                self.mutex.lock()
                while self._is_paused:
                    self.pause_cond.wait(self.mutex)
                self.mutex.unlock()

                if not self._is_running:
                    return None

                self.progress.emit(name, index + 1, total)

                info = {
                    "文件名": name,
                    "路径": root,
                    "类型": ext.lstrip('.'),
                    "大小(MB)": round(os.path.getsize(path) / (1024 * 1024), 2),
                    "时长": "",
                    "关键词": ",",
                    "预览图": None
                }

                try:
                    CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
                    # 获取视频时长
                    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
                    result = subprocess.run(
                        shlex.split(cmd),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, creationflags=CREATE_NO_WINDOW
                    )
                    duration = float(result.stdout.decode().strip())
                    info["时长"] = format_duration(duration)

                    # 生成预览图（取中间帧）
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                        img_path = tmp_img.name

                    cmd = f'ffmpeg -y -ss {duration / 2} -i "{path}" -vframes 1 "{img_path}"'
                    subprocess.run(
                        shlex.split(cmd),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW, check=True
                    )

                    with open(img_path, 'rb') as f:
                        info["预览图"] = f.read()
                    os.remove(img_path)

                except subprocess.CalledProcessError as e:
                    print(f"[ffprobe error] {path}: {e.output.decode()}")
                    info["时长"] = "读取失败"

                except Exception as e:
                    print(f"[exception] {path}: {str(e)}")
                    info["时长"] = "读取失败"

                return info

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(process_file, (i, path)): path for i, path in enumerate(video_files)}
                for future in as_completed(futures):
                    info = future.result()
                    if info:
                        collected.append(info)
                        if self.mode in (0, 2):
                            self.itemReady.emit(info)

            self.finished.emit(collected, self.folder)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False
        self.resume()

    def pause(self):
        self.mutex.lock()
        self._is_paused = True
        self.mutex.unlock()

    def resume(self):
        self.mutex.lock()
        self._is_paused = False
        self.mutex.unlock()
        self.pause_cond.wakeAll()
