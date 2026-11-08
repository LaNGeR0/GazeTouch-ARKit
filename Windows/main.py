from __future__ import annotations

import ctypes
import os
import sys
import traceback


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    if os.name != "nt":
        print("GazeTouch is intended for Windows 10/11.")
        return 2
    enable_dpi_awareness()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from gaze_touch.ui import MainWindow
        app = QApplication(sys.argv)
        app.setApplicationName("GazeTouch")
        app.setOrganizationName("GazeTouch")
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "GazeTouch error", details)
        except Exception:
            print(details, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
