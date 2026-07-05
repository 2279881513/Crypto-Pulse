"""pytest 共享配置 — 确保 cryptopulse 模块可导入"""
import os
import sys

# pytest 运行时当前目录是 cryptopulse/（包名与目录名相同）
# Python 在 sys.path[0]='.' 中查找 'cryptopulse' 时会找 ./cryptopulse/ 不存在
# 解决方案：将父目录加入 sys.path 并移除当前目录的干扰
_test_root = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_test_root)   # cryptopulse/ repo root
_parent_dir = os.path.dirname(_project_root)  # kan/

# 确保父目录在 sys.path 中
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 移除当前目录（包名冲突）
cwd = os.getcwd()
while cwd in sys.path:
    sys.path.remove(cwd)
