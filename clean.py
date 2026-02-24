#!/usr/bin/env python3
"""
清理脚本：删除项目中的 __pycache__ 目录、temp 目录、.db 数据库文件和 .json 配置文件
"""

import os
import shutil
from pathlib import Path


def find_and_remove_pycache(root_dir):
    """递归查找并删除所有 __pycache__ 目录"""
    removed = []
    for pycache_dir in Path(root_dir).rglob('__pycache__'):
        if pycache_dir.is_dir():
            try:
                shutil.rmtree(pycache_dir)
                removed.append(str(pycache_dir))
                print(f"[已删除] __pycache__: {pycache_dir}")
            except Exception as e:
                print(f"[错误] 无法删除 {pycache_dir}: {e}")
    return removed


def find_and_remove_by_extension(root_dir, extensions):
    """根据扩展名查找并删除文件"""
    removed = []
    for ext in extensions:
        for file_path in Path(root_dir).rglob(f'*{ext}'):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    removed.append(str(file_path))
                    print(f"[已删除] {ext} 文件: {file_path}")
                except Exception as e:
                    print(f"[错误] 无法删除 {file_path}: {e}")
    return removed


def find_and_remove_temp_dirs(root_dir):
    """递归查找并删除所有 temp 目录"""
    removed = []
    for temp_dir in Path(root_dir).rglob('temp'):
        if temp_dir.is_dir():
            try:
                shutil.rmtree(temp_dir)
                removed.append(str(temp_dir))
                print(f"[已删除] temp 目录: {temp_dir}")
            except Exception as e:
                print(f"[错误] 无法删除 {temp_dir}: {e}")
    return removed


def main():
    """主函数"""
    # 获取脚本所在目录作为根目录
    root_dir = Path(__file__).parent
    
    print("=" * 50)
    print("开始清理项目...")
    print("=" * 50)
    
    # 1. 删除 __pycache__ 目录
    print("\n>>> 正在清理 __pycache__ 目录...")
    pycache_removed = find_and_remove_pycache(root_dir)
    
    # 2. 删除 temp 目录
    print("\n>>> 正在清理 temp 目录...")
    temp_removed = find_and_remove_temp_dirs(root_dir)
    
    # 3. 删除 .db 文件
    print("\n>>> 正在清理 .db 数据库文件...")
    db_removed = find_and_remove_by_extension(root_dir, ['.db'])
    
    # 4. 删除 .json 配置文件
    print("\n>>> 正在清理 .json 配置文件...")
    json_removed = find_and_remove_by_extension(root_dir, ['.json'])
    
    # 统计结果
    print("\n" + "=" * 50)
    print("清理完成！")
    print("=" * 50)
    print(f"删除的 __pycache__ 目录: {len(pycache_removed)} 个")
    print(f"删除的 temp 目录: {len(temp_removed)} 个")
    print(f"删除的 .db 文件: {len(db_removed)} 个")
    print(f"删除的 .json 文件: {len(json_removed)} 个")
    print(f"总计删除: {len(pycache_removed) + len(temp_removed) + len(db_removed) + len(json_removed)} 项")


if __name__ == '__main__':
    main()
