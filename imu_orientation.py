"""Six-axis attitude baseline: gyro integration with gravity feedback.

The installed Nano library reports a left-handed XYZ convention. Convert both
vectors to the physical right-handed board frame BEFORE quaternion arithmetic:
u = displayed Y (board right), v = displayed X (away from USB), w = displayed Z.
Quaternion order is (w, x, y, z); it rotates board vectors into a Z-up world.
Yaw is relative, because the BLE packet does not contain a magnetometer.
"""
import math

import numpy as np


def multiply(a, b):
    w, x, y, z = a
    s, u, v, t = b
    return np.array([w*s-x*u-y*v-z*t, w*u+x*s+y*t-z*v,
                     w*v-x*t+y*s+z*u, w*t+x*v-y*u+z*s])


def rotation_matrix(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
        [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)],
    ])


def gravity_quaternion(acceleration, yaw=0.0):
    """Align measured upward specific force with world up; yaw is chosen."""
    x, y, z = acceleration
    roll = math.atan2(y, z)
    pitch = math.atan2(-x, math.hypot(y, z))
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    return np.array([cr*cp*cy+sr*sp*sy, sr*cp*cy-cr*sp*sy,
                     cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy])


class AttitudeEstimator:
    """Mahony-style proportional gravity feedback, using elapsed BOARD time.

    A one-second stationary window estimates gyro zero on startup or request.
    It runs once, rather than continuously absorbing real slow rotations.
    Large acceleration magnitudes reduce gravity feedback. A long packet gap
    skips unknown rotation and reacquires tilt instead of integrating stale data.
    """

    def __init__(self, gain=2.5):
        self.gain = gain
        self.quaternion = np.array([1.0, 0.0, 0.0, 0.0])
        self.bias_dps = np.zeros(3)
        self.previous_time = None
        self.previous_gyro = None
        self.heading_reference = 0.0
        self.ready = False
        self.updates = 0
        self.gap_resets = 0
        self.acceleration_weight = 0.0
        self.request_calibration()

    def request_calibration(self):
        self.calibrating = True
        self.calibration_progress = 0.0
        self._quiet_since = None
        self._quiet_acceleration = None
        self._quiet_gyros = []

    @staticmethod
    def heading(matrix):
        if math.hypot(matrix[0, 0], matrix[1, 0]) > 1e-5:
            return math.atan2(matrix[1, 0], matrix[0, 0])
        return math.atan2(-matrix[0, 1], matrix[1, 1])

    def zero_heading(self):
        if self.ready:
            self.heading_reference = self.heading(rotation_matrix(self.quaternion))

    @property
    def matrix(self):
        c, s = math.cos(self.heading_reference), math.sin(self.heading_reference)
        reference = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        return reference @ rotation_matrix(self.quaternion)

    @property
    def angles_degrees(self):
        r = self.matrix
        # ZYX Euler angles in the physical board frame: roll about displayed Y,
        # pitch about displayed X, and yaw about the fixed world vertical.
        return tuple(math.degrees(a) for a in (
            math.atan2(r[2, 1], r[2, 2]),
            math.asin(float(np.clip(-r[2, 0], -1, 1))),
            self.heading(r),
        ))

    def _calibrate(self, acceleration, gyro, elapsed):
        magnitude = float(np.linalg.norm(acceleration))
        quiet = abs(magnitude-1.0) < 0.06 and np.linalg.norm(gyro) < 2.0
        if quiet and self._quiet_acceleration is not None:
            direction = acceleration/magnitude
            quiet = np.dot(direction, self._quiet_acceleration) > math.cos(math.radians(2))
        if not quiet:
            self._quiet_since = None
            self._quiet_acceleration = None
            self._quiet_gyros.clear()
            self.calibration_progress = 0.0
            return
        if self._quiet_since is None:
            self._quiet_since = elapsed
            self._quiet_acceleration = acceleration/magnitude
        self._quiet_gyros.append(gyro)
        self.calibration_progress = min(1.0, elapsed-self._quiet_since)
        if self.calibration_progress >= 1.0 and len(self._quiet_gyros) >= 10:
            self.bias_dps = np.mean(self._quiet_gyros, axis=0)
            self.calibrating = False
            self._quiet_gyros.clear()
            self.zero_heading()

    def update(self, sample, elapsed):
        acceleration = np.array([sample.ay_g, sample.ax_g, sample.az_g])
        gyro = np.array([sample.gy_dps, sample.gx_dps, sample.gz_dps])
        if not np.all(np.isfinite(acceleration)) or not np.all(np.isfinite(gyro)):
            return
        norm = float(np.linalg.norm(acceleration))
        dt = None if self.previous_time is None else elapsed-self.previous_time
        self.previous_time = elapsed
        if not self.ready:
            if not 0.75 <= norm <= 1.25:
                return
            self.quaternion = gravity_quaternion(acceleration)
            self.ready = True
            self.zero_heading()
            dt = None  # No attitude existed before this valid initialization.
        if dt is not None and dt > 0.25:
            self.gap_resets += 1
            self.previous_gyro = None
            if 0.75 <= norm <= 1.25:
                yaw = self.heading(rotation_matrix(self.quaternion))
                self.quaternion = gravity_quaternion(acceleration, yaw)
            if self.calibrating:
                self.request_calibration()
        if self.calibrating:
            self._calibrate(acceleration, gyro, elapsed)
        self.acceleration_weight = float(np.clip((0.25-abs(norm-1.0))/0.17, 0, 1))
        if dt is not None and 0 < dt <= 0.25:
            mean_gyro = gyro if self.previous_gyro is None else (gyro+self.previous_gyro)/2
            omega = np.deg2rad(mean_gyro-self.bias_dps)
            if self.acceleration_weight > 0 and norm > 1e-6:
                predicted_up = rotation_matrix(self.quaternion)[2, :]
                error = np.cross(acceleration/norm, predicted_up)
                omega += self.gain*self.acceleration_weight*error
            speed = float(np.linalg.norm(omega))
            if speed > 1e-12:
                half_angle = speed*dt/2
                delta = np.concatenate(([math.cos(half_angle)],
                                        omega*(math.sin(half_angle)/speed)))
                self.quaternion = multiply(self.quaternion, delta)
                self.quaternion /= np.linalg.norm(self.quaternion)
        self.previous_gyro = gyro
        self.updates += 1
