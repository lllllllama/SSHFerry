import sys
print("Python:", sys.executable, sys.version)
try:
    import paramiko
    print("paramiko:", paramiko.__version__)
except ImportError:
    print("paramiko: NOT INSTALLED")
try:
    import pytest
    print("pytest:", pytest.__version__)
except ImportError:
    print("pytest: NOT INSTALLED")
try:
    import PySide6
    print("PySide6:", PySide6.__version__)
except ImportError:
    print("PySide6: NOT INSTALLED")
