from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget
)

from .calibration import GazeCalibration
from .filters import StableFilter
from .gestures import PinchGate
from .mouse import WindowsMouse
from .receiver import ARKitReceiver


def calibration_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GazeTouch"
    root.mkdir(parents=True, exist_ok=True)
    return root / "arkit_calibration.json"


class CalibrationOverlay(QWidget):
    finished = Signal(object)

    AXIS = (0.06, 0.35, 0.65, 0.94)
    TARGETS = [(x, y) for y in AXIS for x in AXIS]
    SETTLE = 0.65
    SAMPLE = 1.25
    MAX_TIME = 3.0

    def __init__(self, receiver: ARKitReceiver) -> None:
        super().__init__(None)
        self.receiver = receiver
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.virtualGeometry())
        self.index = 0
        self.started = time.perf_counter()
        self.samples: list[tuple[float, float]] = []
        self.completed: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.message = "Смотрите только глазами на точку"
        self.last_sample = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(35)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tick(self) -> None:
        if self.index >= len(self.TARGETS):
            self.finish(self.completed)
            return
        now = time.perf_counter()
        elapsed = now - self.started
        if elapsed >= self.SETTLE:
            sample = self.receiver.latest_gaze()
            if sample and sample[1] > self.last_sample:
                self.samples.append(sample[0])
                self.last_sample = sample[1]
        enough = len(self.samples) >= 8
        if (elapsed >= self.SETTLE + self.SAMPLE and enough) or (elapsed >= self.MAX_TIME and enough):
            feature = (float(np.median([p[0] for p in self.samples])),
                       float(np.median([p[1] for p in self.samples])))
            self.completed.append((feature, self.TARGETS[self.index]))
            self.index += 1
            self.started = now
            self.samples = []
            self.last_sample = 0.0
            self.message = "Хорошо. Переведите взгляд на следующую точку"
        elif elapsed >= self.MAX_TIME:
            self.finish(None)
            QMessageBox.warning(
                None, "Нет данных взгляда",
                "iPhone не прислал достаточно измерений. Проверьте Wi-Fi и положение телефона."
            )
            return
        elif elapsed < self.SETTLE:
            self.message = "Переведите глаза на точку и удерживайте взгляд"
        else:
            self.message = f"Измеряю взгляд… {len(self.samples)}"
        self.update()

    def finish(self, result: object | None) -> None:
        self.timer.stop()
        self.hide()
        self.finished.emit(result)
        self.deleteLater()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.finish(None)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(5, 10, 18, 235))
        p.setPen(QColor(245, 248, 252))
        p.setFont(QFont("Segoe UI", 22, QFont.Weight.DemiBold))
        p.drawText(0, 50, self.width(), 40, Qt.AlignmentFlag.AlignHCenter, "Калибровка взгляда")
        p.setPen(QColor(185, 198, 216))
        p.setFont(QFont("Segoe UI", 12))
        p.drawText(0, 96, self.width(), 30, Qt.AlignmentFlag.AlignHCenter, self.message)
        p.drawText(0, 130, self.width(), 24, Qt.AlignmentFlag.AlignHCenter,
                   f"Точка {min(self.index + 1, 16)} из 16 · Esc — отмена")
        if self.index < len(self.TARGETS):
            tx, ty = self.TARGETS[self.index]
            cx, cy = int(tx * self.width()), int(ty * self.height())
            p.setPen(QPen(QColor(255, 255, 255, 120), 2))
            p.setBrush(QColor(50, 155, 245, 80))
            p.drawEllipse(cx - 26, cy - 26, 52, 52)
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.setBrush(QColor(55, 165, 255))
            p.drawEllipse(cx - 10, cy - 10, 20, 20)
            p.drawLine(cx - 38, cy, cx + 38, cy)
            p.drawLine(cx, cy - 38, cx, cy + 38)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GazeTouch · iPhone ARKit")
        self.setMinimumSize(760, 560)
        self.receiver = ARKitReceiver(port=50555)
        self.receiver.status_changed.connect(self._status)
        self.receiver.packet_changed.connect(self._packet)
        self.receiver.start()

        self.mouse = WindowsMouse()
        self.left, self.top, self.width_px, self.height_px = self.mouse.bounds()
        self.calibration = GazeCalibration.load(calibration_file())
        self.filter_x, self.filter_y = StableFilter(), StableFilter()
        self.gate = PinchGate()
        self.enabled = False
        self.overlay: CalibrationOverlay | None = None
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._process)
        self.timer.start()

        self.f8 = QShortcut(QKeySequence("F8"), self)
        self.f8.activated.connect(self.toggle_control)

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#101722; color:#edf2f8; font-family:'Segoe UI'; }
            QFrame#panel { background:#172231; border:1px solid #29384b; border-radius:16px; }
            QLabel#muted { color:#a9b7c9; font-size:12px; }
            QLabel#title { color:#f5f8fc; font-size:25px; font-weight:700; }
            QPushButton { background:#2c8de3; color:white; border:0; border-radius:9px; padding:11px 14px; font-weight:650; }
            QPushButton#secondary { background:#28374a; border:1px solid #3b5069; }
            QSlider::groove:horizontal { height:5px; border-radius:2px; background:#35465b; }
            QSlider::handle:horizontal { background:#59b1ff; width:15px; margin:-6px 0; border-radius:7px; }
            QCheckBox { color:#dce6f2; spacing:8px; }
        """)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("GazeTouch")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("iPhone Air · ARKit · взгляд управляет курсором · щипок выполняет левый клик")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("panel")
        p = QVBoxLayout(panel)
        p.setContentsMargins(18, 18, 18, 18)
        p.setSpacing(10)
        self.connection_label = QLabel("Запускаю UDP-приёмник · порт 50555")
        self.face_label = QLabel("Лицо: ожидание iPhone")
        self.hand_label = QLabel("Рука: ожидание iPhone")
        self.gaze_label = QLabel("Взгляд: —")
        self.pinch_label = QLabel("Щипок: —")
        self.packet_label = QLabel("Пакеты: 0")
        for label in (self.connection_label, self.face_label, self.hand_label,
                      self.gaze_label, self.pinch_label, self.packet_label):
            label.setObjectName("muted")
            p.addWidget(label)
        layout.addWidget(panel)

        row = QHBoxLayout()
        self.calibrate_btn = QPushButton("Калибровать · 16 точек")
        self.calibrate_btn.setObjectName("secondary")
        self.calibrate_btn.clicked.connect(self.start_calibration)
        self.control_btn = QPushButton("Начать управление")
        self.control_btn.clicked.connect(self.toggle_control)
        row.addWidget(self.calibrate_btn)
        row.addWidget(self.control_btn)
        layout.addLayout(row)

        self.gaze_check = QCheckBox("Перемещать курсор взглядом")
        self.gaze_check.setChecked(True)
        self.gaze_check.stateChanged.connect(lambda _: self._settings_changed())
        self.hand_check = QCheckBox("Кликать щипком")
        self.hand_check.setChecked(True)
        self.hand_check.stateChanged.connect(lambda _: self._settings_changed())
        layout.addWidget(self.gaze_check)
        layout.addWidget(self.hand_check)

        self.sensitivity = self._add_slider(layout, "Чувствительность", 50, 200, 100)
        self.smoothing = self._add_slider(layout, "Стабилизация", 0, 100, 85)
        self.pinch = self._add_slider(layout, "Порог щипка", 15, 50, 30)

        help_label = QLabel(
            "1. Открой GazeTouch Sensor на iPhone и введи IPv4 компьютера, порт 50555.\\n"
            "2. Дождись статуса «Лицо: найдено», затем выполни калибровку.\\n"
            "F8 — включить/приостановить курсор. Esc — отменить калибровку."
        )
        help_label.setObjectName("muted")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        layout.addStretch(1)
        self.setCentralWidget(central)

    def _add_slider(self, layout: QVBoxLayout, name: str, minimum: int,
                    maximum: int, initial: int) -> QSlider:
        title = QLabel(f"{name}: {initial}%")
        title.setObjectName("muted")
        layout.addWidget(title)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(initial)
        slider.valueChanged.connect(lambda v, lab=title, nm=name: lab.setText(f"{nm}: {v}%"))
        layout.addWidget(slider)
        return slider

    def _settings_changed(self) -> None:
        self.filter_x.set_smoothing(self.smoothing.value())
        self.filter_y.set_smoothing(self.smoothing.value())

    def _status(self, message: str) -> None:
        self.connection_label.setText(message)

    def _packet(self, face: bool, hand: bool, gaze: str, pinch: str) -> None:
        self.face_label.setText("Лицо: найдено" if face else "Лицо: не найдено")
        self.hand_label.setText("Рука: найдена" if hand else "Рука: не найдена")
        self.gaze_label.setText(f"Вектор взгляда: {gaze}")
        self.pinch_label.setText(f"Рука: {pinch}")
        self.packet_label.setText(f"Пакеты: {self.receiver.snapshot()['packets']}")

    def start_calibration(self) -> None:
        snap = self.receiver.snapshot()
        if not snap["face"]:
            QMessageBox.warning(self, "Нет iPhone-сигнала",
                                "Сначала открой приложение GazeTouch Sensor на iPhone и подключи его к этому ПК.")
            return
        self.set_control_state(False)
        self.calibrate_btn.setEnabled(False)
        self.overlay = CalibrationOverlay(self.receiver)
        self.overlay.finished.connect(self._calibration_finished)
        self.overlay.show()

    def _calibration_finished(self, raw: object) -> None:
        self.overlay = None
        self.calibrate_btn.setEnabled(True)
        if raw is None:
            QMessageBox.warning(self, "Калибровка не завершена", "Не удалось собрать данные на всех точках. Проверь телефон и повтори.")
            return
        try:
            model = GazeCalibration.fit(list(raw))
            model.save(calibration_file())
            self.calibration = model
            QMessageBox.information(self, "Готово", "Калибровка сохранена. Теперь включи управление.")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка калибровки", str(exc))

    def set_control_state(self, enabled: bool) -> None:
        self.enabled = enabled
        self.control_btn.setText("Остановить управление" if enabled else "Начать управление")
        self.filter_x.reset()
        self.filter_y.reset()
        if not enabled:
            self.gate.reset()

    def toggle_control(self) -> None:
        if not self.enabled:
            if self.calibration is None:
                QMessageBox.information(self, "Сначала калибровка", "Сначала откалибруй взгляд по 16 точкам.")
                return
            if self.gaze_check.isChecked() and not self.receiver.snapshot()["face"]:
                QMessageBox.warning(self, "Нет сигнала", "iPhone пока не передаёт данные взгляда.")
                return
        self.set_control_state(not self.enabled)

    def _process(self) -> None:
        if not self.enabled:
            return
        snap = self.receiver.snapshot()
        now = time.perf_counter()
        sample = self.receiver.latest_gaze()
        if self.gaze_check.isChecked() and sample is not None and self.calibration is not None:
            nx, ny = self.calibration.predict(sample[0])
            sensitivity = self.sensitivity.value() / 100.0
            nx = max(0.0, min(1.0, 0.5 + (nx - 0.5) * sensitivity))
            ny = max(0.0, min(1.0, 0.5 + (ny - 0.5) * sensitivity))
            tx = self.left + nx * (self.width_px - 1)
            ty = self.top + ny * (self.height_px - 1)
            sx = self.filter_x.filter(tx, now)
            sy = self.filter_y.filter(ty, now)
            self.mouse.move_to(
                int(max(self.left, min(self.left + self.width_px - 1, sx))),
                int(max(self.top, min(self.top + self.height_px - 1, sy))),
            )
        elif sample is None:
            self.filter_x.reset()
            self.filter_y.reset()

        pinch_ratio = snap["pinch"] if snap["hand"] else None
        should_click = self.gate.update(
            pinch_ratio,
            self.pinch.value() / 100.0,
            0.60,
            now,
            enabled=self.hand_check.isChecked()
        )
        if should_click:
            self.mouse.left_click()

    def closeEvent(self, event: Any) -> None:
        self.set_control_state(False)
        self.receiver.stop()
        self.receiver.wait(1500)
        if self.overlay is not None:
            self.overlay.close()
        super().closeEvent(event)
