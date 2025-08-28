# main.py
import sys

from PyQt6.QtWidgets import QApplication

from core.WorkerThread import check_ffmpeg_exists  # ✅ 导入自检函数
from ui.main_window import FileCollectorApp

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ✅ 启动时检查 ffmpeg/ffprobe 是否存在
    check_ffmpeg_exists(gui_mode=True)

    win = FileCollectorApp()
    win.show()
    sys.exit(app.exec())
