# Project Path: 打包程序.py
import os
import shutil

import PyInstaller.__main__


def main():
    base_dir = os.path.abspath(".")
    resource_path = os.path.join(base_dir, "resources")
    PyInstaller.__main__.run([
        'main.py',
        '--name=MediaInfoCollector',
        '--windowed',
        f'--add-data={resource_path}{os.pathsep}resources'

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
