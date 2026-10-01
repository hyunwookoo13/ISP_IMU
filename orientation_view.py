"""Perspective 3D board view rendered with Qt, without an OpenGL dependency."""
import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

AXIS_COLORS = ("#2563eb", "#059669", "#ea580c")


class BoardView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(260, 200)
        self.rotation = np.eye(3)
        self.ready = False
        self.paint_count = 0
        self.setAccessibleName("실제 BLE 측정값에서 추정한 보드의 3D 자세와 X Y Z 축")

    def set_pose(self, rotation, ready):
        self.rotation = np.array(rotation, copy=True)
        self.ready = ready
        self.update()

    def paintEvent(self, _event):
        self.paint_count += 1
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        width, height = self.width(), self.height()
        center = QPointF(width/2, height*0.52)
        scale = min(width/6.2, height/5.8)
        eye = np.array([4.4, -7.4, 6.4])
        distance = float(np.linalg.norm(eye))
        direction = eye/distance
        right = np.cross([0, 0, 1], direction)
        right /= np.linalg.norm(right)
        up = np.cross(direction, right)

        def project(point):
            p = np.asarray(point)
            depth = distance-np.dot(p, direction)
            perspective = distance/max(depth, 1.0)
            return QPointF(center.x()+np.dot(p, right)*scale*perspective,
                           center.y()-np.dot(p, up)*scale*perspective)

        def segment(a, b, color, thickness=1):
            painter.setPen(QPen(QColor(color), thickness))
            painter.drawLine(project(a), project(b))

        # The ground stays fixed while the board and its sensor axes rotate.
        floor = -0.38
        for coordinate in np.linspace(-2.8, 2.8, 8):
            segment([coordinate, -2.8, floor], [coordinate, 2.8, floor], "#e4ebf2")
            segment([-2.8, coordinate, floor], [2.8, coordinate, floor], "#e4ebf2")

        faces = []

        def box(left, front, bottom, right_edge, back, top, color, board=False):
            vertices = np.array([[left, front, bottom], [right_edge, front, bottom],
                                 [right_edge, back, bottom], [left, back, bottom],
                                 [left, front, top], [right_edge, front, top],
                                 [right_edge, back, top], [left, back, top]])
            world = vertices @ self.rotation.T
            base = QColor(color)
            for indices, light in [((0, 3, 2, 1), .68), ((0, 1, 5, 4), .78),
                                   ((1, 2, 6, 5), .86), ((2, 3, 7, 6), .82),
                                   ((3, 0, 4, 7), .74), ((4, 5, 6, 7), 1.0)]:
                points = world[list(indices)]
                shade = QColor.fromRgbF(base.redF()*light, base.greenF()*light,
                                        base.blueF()*light)
                faces.append((board, float(np.mean(points @ direction)), points, shade))

        box(-.69, -1.72, -.08, .69, 1.72, .01, "#0f8994", board=True)
        # BLE radio, antenna, IMU, reset button, and recognizable USB end.
        box(-.48, .45, .01, .48, 1.25, .18, "#dce4eb")
        box(-.48, 1.25, .01, .48, 1.57, .065, "#79b885")
        box(-.24, -.22, .01, .20, .22, .12, "#344459")
        box(-.20, -.93, .01, .20, -.57, .12, "#d3dce4")
        box(-.31, -1.90, .01, .31, -1.37, .18, "#c9d4df")
        box(-.23, -1.915, .045, .23, -1.90, .125, "#344459")
        for x in [-.57, .57]:
            for y in np.linspace(-1.52, 1.52, 14):
                box(x-.055, y-.045, .011, x+.055, y+.045, .023, "#e5c57b")
        component_face_visible = np.dot(self.rotation[:, 2], direction) >= 0
        # The PCB is a large occluding plane: paint it beneath raised components
        # on the front, and above them when looking at the back.
        def depth_key(face):
            board, depth, _vertices, _color = face
            layer = (not board) if component_face_visible else board
            return layer, depth
        for _board, _depth, vertices, color in sorted(faces, key=depth_key):
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([project(p) for p in vertices]))

        font = QFont("Helvetica Neue", 11)
        painter.setFont(font)
        origin = self.rotation @ np.array([0, 0, .21])
        # Display X = length, display Y = width; both match the raw signal plots.
        for axis, vector, color in zip("XYZ", ([0, 2.62, 0], [2.36, 0, 0], [0, 0, 2.25]), AXIS_COLORS):
            tip = origin+self.rotation @ np.array(vector)
            a, b = project(origin), project(tip)
            painter.setPen(QPen(QColor(color), 2.8))
            painter.drawLine(a, b)
            dx, dy = b.x()-a.x(), b.y()-a.y()
            length = max(math.hypot(dx, dy), 1)
            ux, uy = dx/length, dy/length
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([b, QPointF(b.x()-ux*10-uy*4, b.y()-uy*10+ux*4),
                                          QPointF(b.x()-ux*10+uy*4, b.y()-uy*10-ux*4)]))
            painter.setPen(QColor(color))
            text_x = min(width-29, max(6, b.x()+ux*13-8))
            text_y = min(height-10, max(18, b.y()+uy*13+5))
            painter.drawText(QPointF(text_x, text_y), "+"+axis)
        usb = project(self.rotation @ np.array([0, -2.17, .07]))
        painter.setPen(QColor("#607187"))
        painter.setFont(QFont("Helvetica Neue", 9))
        painter.drawText(QPointF(max(4, min(width-55, usb.x()-20)),
                                 max(18, min(height-12, usb.y()+12))), "USB")
        if not self.ready:
            painter.setPen(QColor("#607187"))
            painter.drawText(self.rect(), Qt.AlignBottom | Qt.AlignHCenter,
                             "실제 센서 데이터 대기 중")
        painter.end()


class OrientationPanel(QFrame):
    def __init__(self, estimator):
        super().__init__()
        self.estimator = estimator
        self.setObjectName("signalPanel")
        self.setMinimumWidth(290)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title = QLabel("실시간 3D 자세")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        self.note = QLabel("가속도 + 각속도로 추정")
        self.note.setObjectName("panelNote")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.view = BoardView()
        layout.addWidget(self.view, 1)
        legend = QHBoxLayout()
        for axis, meaning, color in zip("XYZ", ("길이", "너비", "수직"), AXIS_COLORS):
            item = QLabel(f"{axis} · {meaning}")
            item.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            legend.addWidget(item)
        layout.addLayout(legend)
        divider = QFrame()
        divider.setStyleSheet("background: #e0e7ef;")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        self.values = []
        for name in ("Roll · Y축", "Pitch · X축", "Yaw · 상대 방향"):
            row = QHBoxLayout()
            caption = QLabel(name)
            caption.setObjectName("panelNote")
            row.addWidget(caption)
            row.addStretch()
            value = QLabel("—")
            value.setStyleSheet("color: #162538; font-size: 20px; font-weight: 600;")
            value.setMinimumWidth(95)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(value)
            self.values.append(value)
            layout.addLayout(row)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.heading_button = QPushButton("방향 0°")
        self.heading_button.clicked.connect(self.zero_heading)
        self.calibration_button = QPushButton("정지 보정")
        self.calibration_button.clicked.connect(self.calibrate)
        for button in (self.heading_button, self.calibration_button):
            button.setStyleSheet("padding: 9px 12px; font-size: 12px;")
            controls.addWidget(button)
        layout.addLayout(controls)
        self.quality = QLabel("실제 센서 데이터 대기 중")
        self.quality.setWordWrap(True)
        self.quality.setStyleSheet("color: #607187; font-size: 12px;")
        layout.addWidget(self.quality)
        limitation = QLabel("Yaw는 시작 방향 기준이며 시간이 지나면 오차가 누적될 수 있습니다.")
        limitation.setObjectName("panelNote")
        limitation.setStyleSheet("font-size: 11px;")
        limitation.setWordWrap(True)
        layout.addWidget(limitation)
        self.refresh()

    def zero_heading(self):
        self.estimator.zero_heading()
        self.refresh()

    def calibrate(self):
        self.estimator.request_calibration()
        self.refresh()

    def refresh(self, stale=False):
        estimator = self.estimator
        self.view.set_pose(estimator.matrix, estimator.ready)
        for value, angle in zip(self.values, estimator.angles_degrees):
            value.setText(f"{angle:+.1f}°" if estimator.ready else "—")
        self.heading_button.setEnabled(estimator.ready and not stale)
        self.calibration_button.setEnabled(estimator.ready and not stale and not estimator.calibrating)
        if not estimator.ready:
            self.quality.setText("실제 센서 데이터 대기 중")
        elif stale:
            self.quality.setText("마지막 수신 자세 · 새 데이터 대기 중")
        elif estimator.calibrating:
            percent = round(estimator.calibration_progress*100)
            self.quality.setText(f"정지 보정 중 {percent}% · 보드를 잠시 가만히 두세요")
        elif estimator.acceleration_weight < 0.5:
            self.quality.setText("움직임이 커 각속도 중심으로 자세를 추정합니다")
        else:
            self.quality.setText("실제 BLE 측정값 · 정지 보정 완료")
