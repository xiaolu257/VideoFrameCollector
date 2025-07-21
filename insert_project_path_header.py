# Project Path: insert_project_path_header.py
import os

# 项目根目录（可根据需要修改）
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
COMMENT_PREFIX = "# Project Path: "


def should_skip(path):
    skip_dirs = {'__pycache__', '.git', '.idea', '.venv'}
    return any(part in skip_dirs for part in path.split(os.sep))


def insert_header(file_path, rel_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 如果第一行已经是注释并包含路径信息，则跳过
        if lines and lines[0].startswith(COMMENT_PREFIX):
            return

        new_header = f"{COMMENT_PREFIX}{rel_path}\n"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_header)
            f.writelines(lines)

        print(f"✔ 插入: {rel_path}")
    except Exception as e:
        print(f"⚠ 跳过 {rel_path}: {e}")


def process_directory(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 过滤不需要处理的目录
        dirnames[:] = [d for d in dirnames if not should_skip(os.path.join(dirpath, d))]

        for filename in filenames:
            if filename.endswith('.py'):
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, PROJECT_ROOT).replace("\\", "/")
                insert_header(full_path, rel_path)


if __name__ == "__main__":
    process_directory(PROJECT_ROOT)
