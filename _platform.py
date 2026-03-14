import platform
import sys
import sysconfig
from pathlib import Path


def main() -> None:
    print("Executable:", sys.executable)
    print("Python:", sys.version.split()[0])
    print("System:", platform.system(), platform.machine())
    print("Platform tag:", sysconfig.get_platform())
    print("Implementation:", sys.implementation.name)
    print("Project dir:", Path(__file__).resolve().parent)
    try:
        from PySide6 import QtCore

        print("PySide6:", QtCore.__version__)
        print("Qt:", QtCore.qVersion())
    except Exception as exc:
        print("PySide6:", f"unavailable ({exc.__class__.__name__}: {exc})")


if __name__ == "__main__":
    main()
