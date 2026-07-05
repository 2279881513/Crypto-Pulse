"""pytest 共享配置 — 确保 cryptopulse 模块可导入"""
import os, sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
