import os
import shutil
import subprocess


def remove_path(path):
    if os.path.isdir(path):
        print(f"删除文件夹: {path}")
        shutil.rmtree(path)
    elif os.path.isfile(path):
        print(f"删除文件: {path}")
        os.remove(path)


def run_pyinstaller():
    # 删除旧的 dist、build、spec 文件
    remove_path("dist")
    remove_path("build")
    remove_path("frame_collector.spec")

    # 构造打包命令
    cmd = [
        "pyinstaller",
        "--clean",
        "--windowed",
        "--name", "frame_collector",
        "main.py"
    ]
    print("开始打包...")
    subprocess.run(cmd, check=True)
    print("打包完成。")

    # 再次清理打包中临时生成的文件
    remove_path("build")
    remove_path("frame_collector.spec")


if __name__ == "__main__":
    try:
        run_pyinstaller()
        print("全部完成！")
    except subprocess.CalledProcessError as e:
        print("打包过程出现错误:", e)
