"""CryptoPulse — python -m cryptopulse 入口"""
import sys
import os

# 确保父目录在 path 中，使 main.py 可导入
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _parent)

# 直接执行 main.py
exec(open(os.path.join(_parent, "main.py")).read())
