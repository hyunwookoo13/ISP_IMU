"""Analytic motion fixtures, never used as data in the live application."""
import math
import unittest

import numpy as np

from imu_orientation import AttitudeEstimator
from imu_protocol import Sample


def sample(ax=0, ay=0, az=1, gx=0, gy=0, gz=0):
    return Sample(0, 0, ax, ay, az, gx, gy, gz)


class OrientationTests(unittest.TestCase):
    def test_static_tilt_axis_mapping_and_gravity_alignment(self):
        for axis in ("X", "Y"):
            estimator = AttitudeEstimator()
            theta = math.radians(35)
            data = sample(ay=-math.sin(theta), az=math.cos(theta)) if axis == "X" else sample(ax=math.sin(theta), az=math.cos(theta))
            estimator.update(data, 0)
            roll, pitch, yaw = estimator.angles_degrees
            self.assertAlmostEqual(pitch if axis == "X" else roll, 35)
            self.assertAlmostEqual(roll if axis == "X" else pitch, 0)
            self.assertAlmostEqual(yaw, 0)
            board_acc = np.array([data.ay_g, data.ax_g, data.az_g])
            np.testing.assert_allclose(estimator.matrix @ board_acc, [0, 0, 1], atol=1e-10)
            self.assertAlmostEqual(np.linalg.det(estimator.matrix), 1)

    def test_gyro_library_axes_map_to_proper_rotations_through_inversion(self):
        # Disable gravity feedback to isolate each gyro axis through a full 180°.
        for axis, expected in [
            ("X", np.diag([-1, 1, -1])),
            ("Y", np.diag([1, -1, -1])),
            ("Z", np.diag([-1, -1, 1])),
        ]:
            estimator = AttitudeEstimator(gain=0)
            motion = sample(**{"g"+axis.lower(): 90})
            estimator.update(motion, 0)
            for step in range(1, 51):
                estimator.update(motion, step*.04)
            np.testing.assert_allclose(estimator.matrix, expected, atol=1e-10)
            self.assertAlmostEqual(np.linalg.norm(estimator.quaternion), 1)

    def test_yaw_uses_board_time_and_can_be_zeroed(self):
        estimator = AttitudeEstimator()
        motion = sample(gz=90)
        estimator.update(motion, 0)
        elapsed = 0
        for dt in [.013, .061, .027, .049]*6 + [.1]:
            elapsed += dt
            estimator.update(motion, elapsed)
        self.assertAlmostEqual(elapsed, 1)
        self.assertAlmostEqual(estimator.angles_degrees[2], 90)
        estimator.zero_heading()
        np.testing.assert_allclose(estimator.matrix, np.eye(3), atol=1e-10)

    def test_translation_does_not_force_a_tilt_when_magnitude_is_invalid(self):
        estimator = AttitudeEstimator()
        estimator.update(sample(), 0)
        for step in range(1, 26):
            estimator.update(sample(ax=2, az=0), step*.04)
        self.assertEqual(estimator.acceleration_weight, 0)
        np.testing.assert_allclose(estimator.matrix, np.eye(3), atol=1e-10)

    def test_stationary_gyro_bias_calibration_limits_yaw_drift(self):
        estimator = AttitudeEstimator()
        rest = sample(gx=.3, gy=-.2, gz=.5)
        for step in range(301):
            estimator.update(rest, step*.04)
        self.assertFalse(estimator.calibrating)
        np.testing.assert_allclose(estimator.bias_dps, [-.2, .3, .5], atol=1e-10)
        self.assertLess(abs(estimator.angles_degrees[2]), .03)

    def test_motion_resets_calibration_window(self):
        estimator = AttitudeEstimator()
        for step in range(10):
            estimator.update(sample(), step*.04)
        estimator.update(sample(gz=30), .4)
        self.assertEqual(estimator.calibration_progress, 0)
        self.assertTrue(estimator.calibrating)

    def test_long_packet_gap_does_not_integrate_stale_rotation(self):
        estimator = AttitudeEstimator(gain=0)
        estimator.update(sample(gz=90), 0)
        estimator.update(sample(gz=90), .1)
        estimator.update(sample(gz=90), 3.1)
        self.assertEqual(estimator.gap_resets, 1)
        self.assertAlmostEqual(estimator.angles_degrees[2], 9)

    def test_upside_down_initialization_is_a_valid_rotation(self):
        estimator = AttitudeEstimator()
        estimator.update(sample(az=-1), 0)
        np.testing.assert_allclose(estimator.matrix @ [0, 0, -1], [0, 0, 1], atol=1e-10)
        self.assertAlmostEqual(np.linalg.det(estimator.matrix), 1)

    def test_gravity_feedback_corrects_a_tilt_error_in_the_right_direction(self):
        estimator = AttitudeEstimator()
        estimator.update(sample(), 0)
        tilted = sample(ax=.5, az=math.sqrt(3)/2)
        for step in range(1, 151):
            estimator.update(tilted, step*.04)
        self.assertAlmostEqual(estimator.angles_degrees[0], 30, delta=.1)

    def test_unreliable_start_waits_for_gravity_without_integrating_old_time(self):
        estimator = AttitudeEstimator()
        estimator.update(sample(az=0, gz=90), 0)
        self.assertFalse(estimator.ready)
        estimator.update(sample(gz=90), .1)
        self.assertTrue(estimator.ready)
        self.assertAlmostEqual(estimator.angles_degrees[2], 0)


if __name__ == "__main__":
    unittest.main()
