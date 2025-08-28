# VideoFrameCollector

一个基于 **PyQt6** 开发的视频帧提取工具，支持多线程高效处理。  
可对所选文件夹下的所有视频批量进行逐帧提取，并支持灵活的截取策略和输出格式。

## ✨ 功能特点

- 📂 **批量处理**：自动扫描所选文件夹下的所有视频文件
- ⚡ **多线程加速**：充分利用 CPU 性能并行处理多个视频
- 🎞️ **灵活截取模式**：
    - 每 **N 秒** 提取一帧
    - 每 **N 帧** 提取一帧
- 🖼️ **多种输出格式**：
    - PNG 无损保存
    - JPG 可自定义压缩质量 (1–100)
- 📑 **输出管理**：
    - 每个视频单独输出到对应文件夹
    - 截取完成后可双击结果记录，快速打开输出目录
- 🔍 **自检功能**：启动时检查 `ffmpeg` / `ffprobe` 是否存在，缺失时弹窗提示

---

## 📦 安装

1. 克隆仓库
   ```bash
   git clone https://github.com/xiaolu257/VideoFrameCollector.git
   cd VideoFrameCollector
   ```

2. 创建虚拟环境（推荐）
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux / MacOS
   venv\Scripts\activate         # Windows
   ```

3. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```

4. 项目内置 **ffmpeg / ffprobe**，用户无需安装或配置系统环境变量。

---

## 🚀 使用方法

1. 启动程序
   ```bash
   python main.py
   ```

2. 在界面中：
    - 选择需要处理的视频文件夹
    - 设置截取模式（每 N 秒 或 每 N 帧）
    - 选择输出格式（PNG 或 JPG）及参数
    - 点击 **开始处理**，等待完成

3. 处理完成后：
    - 输出文件夹会自动生成在指定目录下
    - 在结果表格中双击任意条目即可快速打开对应目录

---

## 🛠️ 打包为可执行文件

如果需要分发给无 Python 环境的用户，可以使用 **PyInstaller** 打包：

```bash
python 打包程序.py
```

生成的可执行文件（VideoFrameCollector.exe）位于 `dist/VideoFrameCollector/` 目录下。  
请确保 `ffmpeg/` 文件夹也随程序一同分发（若打包正常，内置 `ffmpeg` 及 `ffprobe`
应当存在于 `dist/VideoFrameCollector/_internal/ffmpeg` 下）。

如需分享给朋友，可进入 `dist/VideoFrameCollector`，直接压缩成 zip 或 7z 发给对方，让对方解压后进入 `VideoFrameCollector`
文件夹内运行 `VideoFrameCollector.exe`。

---

## 📦 依赖说明

本项目依赖以下 Python 库（已在 `requirements.txt` 中列出）：

- PyQt6
- pyinstaller

⚠️ 注意：

- [ffmpeg](https://ffmpeg.org/) 与 [ffprobe](https://ffmpeg.org/ffprobe.html) 已 **内置在项目中**，无需用户单独下载或安装。
- 程序启动时会自动检查 `ffmpeg` / `ffprobe` 是否存在，缺失时将提示错误。

开发环境依赖：

- [pyinstaller](https://pypi.org/project/pyinstaller/)（仅用于打包）

---

## 📷 截图

### 1️⃣ 界面展示

<img width="1252" height="789" alt="界面展示" src="https://github.com/user-attachments/assets/29f0d7ba-2cc0-45c5-a8f8-88411d80c350" />

### 2️⃣ 选定参数，开始处理

<img width="1252" height="789" alt="选定参数" src="https://github.com/user-attachments/assets/dc35939e-6d78-4f46-ba28-86eceadd0852" />

### 3️⃣ 处理完成

<img width="1249" height="784" alt="处理完成" src="https://github.com/user-attachments/assets/6ca05c6f-3536-4db9-8737-a434830718d5" />

### 4️⃣ 打开 `帧生成` 所在文件夹

（各个视频的截取帧文件夹的所在目录与该视频相对被选择处理的文件夹路径一致，即目录结构一致）  
<img width="789" height="276" alt="打开帧生成所在文件夹" src="https://github.com/user-attachments/assets/736b55b8-4fbb-483e-b0a8-a7cbb45f0e54" />

### 5️⃣ 生成帧一览

<img width="1919" height="1278" alt="生成帧一览" src="https://github.com/user-attachments/assets/12fad228-16b7-44ec-98e7-8920cf6d68bb" />

### 6️⃣ 随机选择图片展示

（图片质量取决于原视频分辨率、程序所选参数为 PNG 还是 JPG，以及 JPG 下的压缩质量）  
<img width="1902" height="998" alt="随机选择图片展示" src="https://github.com/user-attachments/assets/22c80e8b-2d0d-49ba-95ff-b40ba8c52b16" />

---

## 📜 许可证

本项目基于 [MIT License](LICENSE) 开源，欢迎自由使用、修改和分发。

⚠️ 版权格言：
> 盗他人之功，非君子所为；妄称己作，损德亦伤名。  
> 勿窃他人成果，自显其劳；尊重原作者，方成正道。

如您有任何疑问或想交流技术，欢迎联系： [1626309145@qq.com](mailto:1626309145@qq.com)

