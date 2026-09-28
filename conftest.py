# conftest.py 放在仓库根目录的作用：
# pytest 以 prepend 导入模式加载本文件时，会把本目录加入 sys.path，
# 从而使 tests/ 内可以直接 import ragdemo 包（tests/ 自身无 __init__.py）。
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
