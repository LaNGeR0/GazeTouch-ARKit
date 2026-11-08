from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class GazeCalibration:
    mean_x: float
    mean_y: float
    scale_x: float
    scale_y: float
    coef_x: list[float]
    coef_y: list[float]

    @staticmethod
    def _design(x: float, y: float, mx: float, my: float, sx: float, sy: float) -> np.ndarray:
        u = (float(x) - mx) / max(sx, 1e-6)
        v = (float(y) - my) / max(sy, 1e-6)
        return np.array([1.0, u, v, u * v, u * u, v * v], dtype=np.float64)

    @classmethod
    def fit(cls, samples: list[tuple[tuple[float, float], tuple[float, float]]]) -> "GazeCalibration":
        if len(samples) < 12:
            raise ValueError("Нужно не менее 12 успешно собранных точек из 16.")
        gx = np.array([s[0][0] for s in samples], dtype=np.float64)
        gy = np.array([s[0][1] for s in samples], dtype=np.float64)
        tx = np.array([s[1][0] for s in samples], dtype=np.float64)
        ty = np.array([s[1][1] for s in samples], dtype=np.float64)
        mx, my = float(np.mean(gx)), float(np.mean(gy))
        sx, sy = float(np.std(gx)), float(np.std(gy))
        if sx < 1e-5 or sy < 1e-5:
            raise ValueError("Сигнал взгляда слишком мал. Проверьте положение телефона и освещение.")
        matrix = np.vstack([
            cls._design(x, y, mx, my, sx, sy) for x, y in zip(gx, gy)
        ])
        if np.linalg.matrix_rank(matrix) < 6:
            raise ValueError("Сигнал калибровки недостаточно разнообразен. Повторите калибровку.")
        # Light ridge regularization of curvature terms reduces overfit/noisy edge jumps.
        reg = np.diag([0.0, 0.002, 0.002, 0.02, 0.02, 0.02])
        coef_x = np.linalg.solve(matrix.T @ matrix + reg, matrix.T @ tx)
        coef_y = np.linalg.solve(matrix.T @ matrix + reg, matrix.T @ ty)
        return cls(mx, my, sx, sy, coef_x.tolist(), coef_y.tolist())

    def predict(self, features: tuple[float, float]) -> tuple[float, float]:
        row = self._design(
            features[0], features[1], self.mean_x, self.mean_y, self.scale_x, self.scale_y
        )
        x = float(row @ np.asarray(self.coef_x))
        y = float(row @ np.asarray(self.coef_y))
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "GazeCalibration | None":
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            model = cls(
                float(d["mean_x"]), float(d["mean_y"]),
                float(d["scale_x"]), float(d["scale_y"]),
                [float(v) for v in d["coef_x"]], [float(v) for v in d["coef_y"]],
            )
            if len(model.coef_x) != 6 or len(model.coef_y) != 6:
                return None
            return model
        except (OSError, ValueError, KeyError, TypeError):
            return None
