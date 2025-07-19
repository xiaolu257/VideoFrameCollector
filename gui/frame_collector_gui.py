import os
import platform
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

import psutil

from core.frame_collector import collect_frames_batch


class FrameCollectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频帧收集器 v1.0")

        # 居中窗口
        window_width = 900
        window_height = 600
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = int((screen_width - window_width) / 2)
        y = int((screen_height - window_height) / 2)
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        for i in range(7):
            root.rowconfigure(i, weight=0)
        root.rowconfigure(6, weight=1)
        root.columnconfigure(0, weight=1)

        self.stop_flag = False

        # 第一行：文件夹选择
        frame1 = tk.Frame(root)
        frame1.grid(row=0, column=0, pady=10)
        inner1 = tk.Frame(frame1)
        inner1.pack()
        tk.Label(inner1, text="选择文件夹：").pack(side="left")
        self.folder_path = tk.StringVar()
        self.path_entry = tk.Entry(inner1, textvariable=self.folder_path, width=65)
        self.path_entry.pack(side="left", padx=10)
        tk.Button(inner1, text="浏览", command=self.browse_folder).pack(side="left")

        # 第二行：进度条 + 百分比，居中
        frame2 = tk.Frame(root)
        frame2.grid(row=1, column=0, pady=5)

        inner2 = tk.Frame(frame2)
        inner2.pack(anchor="center")  # 👈 保证居中

        self.progress = ttk.Progressbar(inner2, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(side="left")

        self.progress_percent_label = tk.Label(inner2, text="0%", width=6)
        self.progress_percent_label.pack(side="left", padx=10)

        # 第三行：当前进度信息
        self.progress_info_label = tk.Label(root, text="", anchor="center")
        self.progress_info_label.grid(row=2, column=0, sticky="ew", padx=10)

        # 第四行：帧提取模式选择
        frame3 = tk.Frame(root)
        frame3.grid(row=3, column=0, pady=5)
        inner3 = tk.Frame(frame3)
        inner3.pack()
        tk.Label(inner3, text="提取模式：").pack(side="left")
        self.mode_var = tk.StringVar()
        self.mode_combobox = ttk.Combobox(inner3, textvariable=self.mode_var, state="readonly",
                                          values=["每N秒提取一帧", "每N帧提取一帧"], width=25)
        self.mode_combobox.current(0)
        self.mode_combobox.pack(side="left", padx=10)

        tk.Label(inner3, text="间隔值：").pack(side="left")
        self.interval_entry = tk.Entry(inner3, width=10)

        self.interval_entry.insert(0, "1")
        self.interval_entry.pack(side="left", padx=10)

        # 第五行：CPU占用率 + 进程选择
        frame_cpu = tk.Frame(root)
        frame_cpu.grid(row=4, column=0, pady=5)
        inner_cpu = tk.Frame(frame_cpu)
        inner_cpu.pack()

        text = (
            f"CPU占用率：系统 {0:5.1f}% | "
            f"程序单核等效 {0:5.1f}% | "
            f"程序多核合计 {0:6.1f}%({os.cpu_count():2d}核)"
        )
        self.cpu_label = tk.Label(inner_cpu, text=text)
        self.cpu_label.pack(side="left", padx=10)

        tk.Label(inner_cpu, text="最大进程数：").pack(side="left")
        self.max_proc_var = tk.StringVar()
        cpu_count = os.cpu_count()
        default_cpu = max(cpu_count // 3, 1)  # 向下取整，至少为 1
        max_procs = list(range(1, cpu_count + 1))

        self.max_proc_combobox = ttk.Combobox(
            inner_cpu,
            textvariable=self.max_proc_var,
            values=[str(i) for i in max_procs],
            width=5,
            state="readonly"
        )

        # 设置默认选项为 half_cpu（下标从0开始）
        self.max_proc_combobox.current(default_cpu - 1)

        self.max_proc_combobox.pack(side="left", padx=10)

        self.root.after(1000, self.monitor_cpu_usage)  # 延迟1秒启动监控线程，避免UI加载时卡顿

        # 第六行：开始 / 中断 按钮
        frame4 = tk.Frame(root)
        frame4.grid(row=5, column=0, pady=5)
        inner4 = tk.Frame(frame4)
        inner4.pack()
        self.start_button = tk.Button(inner4, text="开始处理", bg="green", fg="white", width=15,
                                      command=self.start_processing_thread)
        self.start_button.pack(side="left", padx=20)
        self.stop_button = tk.Button(inner4, text="中断处理", bg="red", fg="white", width=15,
                                     command=self.stop_processing, state='disabled')
        self.stop_button.pack(side="left", padx=20)

        # 第七行：TreeView展示处理结果
        frame5 = tk.Frame(root)
        frame5.grid(row=6, column=0, sticky="nsew", padx=10, pady=10)
        frame5.rowconfigure(0, weight=1)
        frame5.columnconfigure(0, weight=1)

        self.columns = ("视频文件", "帧数量", "保存路径")
        self.tree = ttk.Treeview(frame5, columns=self.columns, show="headings")
        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=180, anchor="center")

        vsb = ttk.Scrollbar(frame5, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame5, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-1>", self.open_folder)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def monitor_cpu_usage(self):
        current_pid = os.getpid()
        cpu_count = psutil.cpu_count(logical=True)

        def get_all_related_processes():
            """获取当前主进程及其所有子进程的 psutil.Process 对象集合"""
            related = {}
            all_procs = {p.pid: p for p in psutil.process_iter(['pid', 'ppid'])}

            def collect(pid):
                for proc in all_procs.values():
                    if proc.info['ppid'] == pid and proc.pid not in related:
                        related[proc.pid] = proc
                        collect(proc.pid)

            main_proc = psutil.Process(current_pid)
            related[current_pid] = main_proc
            collect(current_pid)
            return related

        def update():
            while not getattr(self, "_stop_monitoring", False):
                try:
                    if not hasattr(self, "cpu_label"):
                        break

                    # 第一步：获取相关进程，初始化采样
                    related_procs = get_all_related_processes()
                    for proc in related_procs.values():
                        try:
                            proc.cpu_percent(interval=None)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass

                    # 第二步：等待采样间隔
                    time.sleep(1.0)

                    # 第三步：再次采样，获取实际 CPU 使用率
                    total_proc_cpu = 0.0
                    for proc in related_procs.values():
                        try:
                            total_proc_cpu += proc.cpu_percent(interval=None)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            continue

                    system_cpu = psutil.cpu_percent(interval=None)  # 同样重新取系统总CPU

                    # 计算单核等效占用（多核总和除以逻辑核心数）
                    proc_cpu_per_core = total_proc_cpu / cpu_count if cpu_count else total_proc_cpu

                    # 显示
                    text = (
                        f"CPU占用率：系统 {system_cpu:5.1f}% | "
                        f"程序单核等效 {proc_cpu_per_core:5.1f}% | "
                        f"程序多核合计 {total_proc_cpu:6.1f}%({cpu_count:2d}核)"
                    )
                    self.cpu_label.config(text=text)

                except (psutil.NoSuchProcess, psutil.AccessDenied, tk.TclError):
                    break

        threading.Thread(target=update, daemon=True).start()

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)

    def on_close(self):
        if self.start_button['state'] == 'disabled':  # 表示处理正在进行
            if self.stop_button['state'] == 'disabled':  # 表示正在中断处理
                messagebox.showinfo("正在中断处理", "为确保您的设备安全，请等待中断处理完成后再退出")
                return
            if messagebox.askyesno("处理中", "当前正在处理视频帧，是否中断并退出？"):
                self.stop_flag = True
                self.progress_info_label.config(text="正在请求中断，请稍候...")
                self.disable_all_widgets()
                self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁用再次点击关闭
                self.root.after(100, self.check_and_close)
            else:
                return  # 用户取消关闭
        else:
            self.root.destroy()  # 直接关闭

    def check_and_close(self):
        # 如果处理已经结束（start_button 被重新启用），安全关闭
        if self.start_button['state'] == 'normal':
            self.root.destroy()
        else:
            # 如果处理尚未结束，稍后再次检查
            self.root.after(100, self.check_and_close)

    def disable_all_widgets(self):
        for child in self.root.winfo_children():
            self.disable_widget_recursively(child)

    def disable_widget_recursively(self, widget):
        try:
            widget.configure(state='disabled')
        except:
            pass
        for child in widget.winfo_children():
            self.disable_widget_recursively(child)

    def stop_processing(self):
        self.stop_flag = True
        self.progress_info_label.config(text="正在请求中断，请稍候...")
        self.stop_button.config(state="disabled")

    def start_processing_thread(self):
        process_count = int(self.max_proc_var.get())
        cpu_physical = psutil.cpu_count(logical=False)
        cpu_logical = psutil.cpu_count(logical=True)

        confirm = messagebox.askyesno(
            "确认开启处理",
            f"当前CPU配置：物理核心 {cpu_physical}，逻辑核心 {cpu_logical}\n"
            f"当前选择的最大并行进程数为 {process_count}。\n\n"
            "建议：\n"
            "- 本程序主要进行视频帧提取，属于CPU密集型任务。\n"
            "- 最佳进程数通常接近CPU的物理核心数，这样可以最大限度利用CPU而避免过多上下文切换。\n"
            "- 进程数并非越多越好，过多会导致系统调度开销增加，反而降低效率。\n"
            "- 保持系统整体CPU占用率在80%~90%可获得最佳处理速度，且电脑不会卡顿。\n"
            "- 如果系统占用率达到100%且感到明显卡顿，建议立即终止操作，降低最大进程数后重试。\n"
            "- 建议初次尝试时选择较小进程数（如2~4），根据体验调整。\n\n"
            "是否确定以当前设置开始处理？"
        )

        if not confirm:
            return
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress["value"] = 0
        self.progress_percent_label.config(text="0%")
        self.progress_info_label.config(text="")
        self.tree.delete(*self.tree.get_children())
        threading.Thread(target=self.start_processing, daemon=True).start()

    def auto_resize_columns(self):
        """自动根据内容调整列宽，每列最小宽度为列名宽度"""
        font = tkfont.nametofont("TkDefaultFont")  # 获取默认字体
        padding = 20  # 每列两侧额外留白像素

        for col in self.columns:
            # 列名宽度 + 留白，作为最小宽度
            min_width = font.measure(col)
            for item in self.tree.get_children():
                cell_text = str(self.tree.set(item, col))
                min_width = max(min_width, font.measure(cell_text))
            self.tree.column(col, width=min_width + padding)

    def add_tree_row(self, result):
        self.tree.insert("", "end", values=(
            result["视频文件"], result["帧数量"], result["保存路径"]
        ))
        self.auto_resize_columns()  # 👈 每次插入后重新调整列宽

    def start_processing(self):
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("错误", "请选择有效的文件夹路径！")
            self.start_button.config(state="normal")
            return

        mode = self.mode_var.get()
        interval_str = self.interval_entry.get()
        if not interval_str.isdigit() or int(interval_str) <= 0:
            messagebox.showerror("错误", "请输入有效的间隔值（正整数）")
            self.start_button.config(state="normal")
            return
        interval = int(interval_str)

        self.stop_flag = False
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(folder, f"帧收集_{now_str}")
        os.makedirs(output_dir, exist_ok=True)

        def result_callback(result):
            self.root.after(0, lambda: self.add_tree_row(result))

        max_workers = int(self.max_proc_var.get())
        collect_frames_batch(folder, output_dir, mode, interval,
                             progress_callback=self.update_progress,
                             stop_flag_func=lambda: self.stop_flag,
                             result_callback=result_callback,
                             max_workers=max_workers)

        # 处理完后
        self.root.after(0, self.finish_processing)

    def finish_processing(self):
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

        if self.stop_flag:
            self.progress_info_label.config(text="处理被中断。")
            messagebox.showinfo("中断", "已中断处理。")
        else:
            self.progress_info_label.config(text="处理完成！")
            messagebox.showinfo("完成", "所有帧提取完成！")

    def update_progress(self, current, total, filename):
        progress_value = int(current * 100 / total)
        self.progress["value"] = progress_value
        self.progress_percent_label.config(text=f"{progress_value}%")
        self.progress_info_label.config(text=f"已完成：{filename} ({current}/{total})")
        self.root.update_idletasks()

    def open_folder(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        folder_path = item["values"][2]
        if not os.path.exists(folder_path):
            messagebox.showerror("错误", "文件夹不存在")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹：{e}")
