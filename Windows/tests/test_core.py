import unittest
from gaze_touch.calibration import GazeCalibration
from gaze_touch.gestures import PinchGate
from gaze_touch.filters import StableFilter


class GazeCalibrationTests(unittest.TestCase):
    def test_four_by_four_grid(self):
        samples = []
        for row, y in enumerate((0.06, 0.35, 0.65, 0.94)):
            for col, x in enumerate((0.06, 0.35, 0.65, 0.94)):
                gx = 0.3 + 0.12 * col + 0.01 * row * col
                gy = -0.2 + 0.11 * row + 0.008 * row * col
                samples.append(((gx, gy), (x, y)))
        model = GazeCalibration.fit(samples)
        for gaze, target in samples:
            x, y = model.predict(gaze)
            self.assertAlmostEqual(x, target[0], delta=0.04)
            self.assertAlmostEqual(y, target[1], delta=0.04)


class PinchTests(unittest.TestCase):
    def test_single_click_per_close_release(self):
        gate = PinchGate()
        self.assertFalse(gate.update(0.7, 0.30, 0.6, 1.0, True))
        self.assertTrue(gate.update(0.2, 0.30, 0.6, 1.1, True))
        self.assertFalse(gate.update(0.18, 0.30, 0.6, 1.2, True))
        self.assertFalse(gate.update(0.7, 0.30, 0.6, 1.3, True))
        self.assertFalse(gate.update(0.2, 0.30, 0.6, 1.4, True))  # cooldown blocks
        self.assertFalse(gate.update(0.7, 0.30, 0.6, 1.7, True))  # release
        self.assertTrue(gate.update(0.2, 0.30, 0.6, 1.8, True))   # next pinch


class FilterTests(unittest.TestCase):
    def test_spike_is_reduced(self):
        f = StableFilter()
        out = [f.filter(v, i / 30) for i, v in enumerate([500, 501, 900, 500, 501])]
        self.assertLess(max(out) - min(out), 50)


if __name__ == "__main__":
    unittest.main()
