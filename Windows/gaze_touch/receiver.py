from __future__ import annotations

import json
import math
import socket
import threading
import time
from typing import Any

from PySide6.QtCore import QThread, Signal


class ARKitReceiver(QThread):
    status_changed = Signal(str)
    packet_changed = Signal(bool, bool, str, str)

    def __init__(self, host: str = "0.0.0.0", port: int = 50555) -> None:
        super().__init__()
        self.host, self.port = host, port
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_gaze: tuple[tuple[float, float], float] | None = None
        self._latest_pinch: float | None = None
        self._face = False
        self._hand = False
        self._last_sequence = -1
        self._packets = 0
        self._last_packet_time = 0.0

    def stop(self) -> None:
        self._stop_event.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "gaze": self._latest_gaze,
                "pinch": self._latest_pinch,
                "face": self._face,
                "hand": self._hand,
                "packets": self._packets,
                "last_packet": self._last_packet_time,
            }

    def latest_gaze(self) -> tuple[tuple[float, float], float] | None:
        with self._lock:
            result = self._latest_gaze
        if result is None or time.perf_counter() - result[1] > 0.35:
            return None
        return result

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.settimeout(0.25)
            self.status_changed.emit(f"Ожидаю iPhone · UDP {self.port}")
            while not self._stop_event.is_set():
                try:
                    payload, peer = sock.recvfrom(16384)
                except socket.timeout:
                    continue
                try:
                    packet = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(packet, dict) or packet.get("version") not in (1, 2):
                    continue

                seq = packet.get("sequence")
                if isinstance(seq, int) and seq <= self._last_sequence:
                    continue
                if isinstance(seq, int):
                    self._last_sequence = seq

                face = bool(packet.get("face_detected", False))
                hand = bool(packet.get("hand_detected", False))
                feature = packet.get("gaze_features")
                now = time.perf_counter()
                gaze = None
                if face and isinstance(feature, (list, tuple)) and len(feature) >= 2:
                    try:
                        gx, gy = float(feature[0]), float(feature[1])
                        if math.isfinite(gx) and math.isfinite(gy) and abs(gx) < 10 and abs(gy) < 10:
                            gaze = ((gx, gy), now)
                    except (TypeError, ValueError):
                        pass
                pinch = packet.get("pinch_ratio")
                try:
                    pinch_val = float(pinch) if pinch is not None else None
                    if pinch_val is not None and (not math.isfinite(pinch_val) or not 0 <= pinch_val <= 3):
                        pinch_val = None
                except (TypeError, ValueError):
                    pinch_val = None

                if self._packets == 0:
                    self.status_changed.emit(f"iPhone подключён · {peer[0]} · UDP {self.port}")
                with self._lock:
                    self._face = face
                    self._hand = hand and pinch_val is not None
                    if gaze is not None:
                        self._latest_gaze = gaze
                    elif not face:
                        self._latest_gaze = None
                    self._latest_pinch = pinch_val if hand else None
                    self._packets += 1
                    self._last_packet_time = now

                gaze_text = f"{feature[0]:+.3f}, {feature[1]:+.3f}" if gaze else "—"
                hand_text = f"щипок {pinch_val:.3f}" if pinch_val is not None and hand else "рука не найдена"
                self.packet_changed.emit(face, hand, gaze_text, hand_text)
        except OSError as exc:
            self.status_changed.emit(f"Ошибка UDP: {exc}")
        finally:
            sock.close()
            self.status_changed.emit("Приёмник остановлен")
