from __future__ import annotations

import ctypes
import os


class WindowsMouse:
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("GazeTouch Windows app requires Windows 10/11.")
        self.user32 = ctypes.windll.user32
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user32.SetCursorPos.restype = ctypes.c_bool
        self.user32.mouse_event.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t
        ]
        self.user32.mouse_event.restype = None

    def bounds(self) -> tuple[int, int, int, int]:
        return (
            self.user32.GetSystemMetrics(self.SM_XVIRTUALSCREEN),
            self.user32.GetSystemMetrics(self.SM_YVIRTUALSCREEN),
            max(1, self.user32.GetSystemMetrics(self.SM_CXVIRTUALSCREEN)),
            max(1, self.user32.GetSystemMetrics(self.SM_CYVIRTUALSCREEN)),
        )

    def move_to(self, x: int, y: int) -> None:
        self.user32.SetCursorPos(int(x), int(y))

    def left_click(self) -> None:
        self.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
