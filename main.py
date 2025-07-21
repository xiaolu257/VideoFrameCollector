# Project Path: main.py
# main.py
import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import FileCollectorApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = FileCollectorApp()
    win.show()
    sys.exit(app.exec())
