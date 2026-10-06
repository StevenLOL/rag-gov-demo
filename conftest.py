# Purpose of placing conftest.py at the repository root:
# when pytest loads this file in prepend import mode, it adds this directory to
# sys.path, so tests/ can import the ragdemo package directly (tests/ itself
# has no __init__.py).
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
