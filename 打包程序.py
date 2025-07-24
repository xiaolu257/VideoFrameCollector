# Project Path: 打包程序.py
import os
import shutil

import PyInstaller.__main__


def main():
    PyInstaller.__main__.run([
        'main.py',
        '--name=MediaInfoCollector',
        '--windowed',
    ])

    # 删除 spec 文件
    spec_file = "MediaInfoCollector.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print(f"已删除：{spec_file}")

    # 删除 build 目录及其所有内容
    build_dir = "build"
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        print(f"已删除目录：{build_dir}/")


if __name__ == "__main__":
    main()
