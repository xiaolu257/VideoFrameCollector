import hashlib
import os
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager

import cv2
import psutil


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
        # 🔁 提前检查中断信号，提升响应速度
        if stop_event.is_set():
            break

        ret, frame = cap.read()

        # 🔁 读取失败 或 中断信号
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
        stop_event = manager.Event()  # ✅ 用于跨进程控制中断

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
                # ✅ 每个任务返回前都可以被中断
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
