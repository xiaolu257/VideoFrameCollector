import sys
import tkinter as tk

from gui.frame_collector_gui import FrameCollectorApp


def main():
    root = tk.Tk()
    app = FrameCollectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    # 打包后多进程必需
    if getattr(sys, 'frozen', False):
        from multiprocessing import freeze_support

        freeze_support()
    main()
