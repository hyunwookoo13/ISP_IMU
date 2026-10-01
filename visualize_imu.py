#!/usr/bin/env python3
"""Live native IMU plots backed exclusively by real BLE notifications."""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import shutil
import signal
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from bleak import BleakClient
from PySide6.QtCore import QFileInfo, QLibraryInfo, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)
from qasync import QEventLoop

from imu_protocol import DATA_UUID, StreamStats, decode_notification
from imu_discovery import choose_device, scan_imu_devices
from imu_orientation import AttitudeEstimator
from orientation_view import OrientationPanel
from receive_imu import CSV_FIELDS

PROJECT_DIR = Path(__file__).resolve().parent
AXIS_COLORS = ("#2563eb", "#059669", "#ea580c")
STYLE = """
QMainWindow, QWidget#root { background: #edf2f7; color: #162538; }
QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Helvetica Neue', sans-serif; }
QFrame#header { background: #ffffff; border-bottom: 1px solid #dbe3ec; }
QLabel#brand { color: #ffffff; background: #087f8c; border-radius: 9px;
              font-size: 15px; font-weight: 700; }
QLabel#title { color: #162538; font-size: 25px; font-weight: 700; }
QLabel#subtitle { color: #607187; font-size: 13px; }
QPushButton { background: #162538; color: #ffffff; border: none;
              border-radius: 8px; padding: 10px 19px; font-size: 14px; font-weight: 600; }
QPushButton:hover { background: #28445f; }
QPushButton:disabled { background: #8896a6; }
QFrame#rail { background: #162538; border-radius: 12px; }
QLabel#railCaption { color: #9eb2c9; font-size: 13px; }
QLabel#metric { color: #ffffff; font-size: 31px; font-weight: 600; }
QLabel#metricUnit { color: #9eb2c9; font-size: 13px; }
QLabel#railTitle { color: #ffffff; font-size: 15px; font-weight: 600; }
QFrame#railDivider { background: #344459; max-height: 1px; }
QFrame#signalPanel { background: #ffffff; border: 1px solid #dbe3ec; border-radius: 12px; }
QLabel#panelTitle { color: #162538; font-size: 19px; font-weight: 600; }
QLabel#panelNote { color: #607187; font-size: 13px; }
QLabel#valueUnit { color: #607187; font-size: 12px; }
QLabel#footer { color: #607187; font-size: 12px; }
"""


def prepare_qt_platform():
    """Qt on this Mac hides plugin files inside .venv; use a visible local cache."""
    if sys.platform != "darwin":
        return
    source = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath)) / "platforms"
    cocoa = source / "libqcocoa.dylib"
    if not cocoa.exists() or not QFileInfo(str(cocoa)).isHidden():
        return
    target = PROJECT_DIR / "runtime" / "qt-plugins" / "platforms"
    target.mkdir(parents=True, exist_ok=True)
    for plugin in source.glob("*.dylib"):
        destination = target / plugin.name
        if destination.exists() and hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(plugin.read_bytes()).digest():
            continue
        # Atomic replacement also leaves any already-running window's image intact.
        temporary = destination.with_suffix(".dylib.tmp")
        shutil.copyfile(plugin, temporary)
        temporary.replace(destination)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(target)


def label(text, name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


class SignalPanel(QFrame):
    def __init__(self, title, unit, precision, min_span):
        super().__init__()
        self.setObjectName("signalPanel")
        self.precision = precision
        self.min_span = min_span
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(label(title, "panelTitle"))
        heading.addStretch()
        heading.addWidget(label("최근 12초", "panelNote"))
        layout.addLayout(heading)

        self.values = []
        numbers = QHBoxLayout()
        numbers.setSpacing(25)
        for axis, color in zip("XYZ", AXIS_COLORS):
            block = QHBoxLayout()
            block.setSpacing(8)
            axis_label = label(axis)
            axis_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
            value = label("—")
            value.setStyleSheet(f"color: {color}; font-size: 21px; font-weight: 600;")
            value.setMinimumWidth(87)
            block.addWidget(axis_label)
            block.addWidget(value)
            block.addWidget(label(unit, "valueUnit"))
            numbers.addLayout(block)
            self.values.append(value)
        numbers.addStretch()
        layout.addLayout(numbers)

        self.plot = pg.PlotWidget(background="#ffffff")
        self.plot.setMinimumHeight(165)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("left", unit, color="#607187", size="13pt")
        self.plot.setLabel("bottom", "보드 시간", units="s", color="#607187", size="11pt")
        axis_font = QFont("Helvetica Neue", 10)
        for name in ("left", "bottom"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen("#ccd7e3"))
            axis.setTextPen(pg.mkPen("#607187"))
            axis.setTickFont(axis_font)
        self.plot.getAxis("left").setWidth(65)
        self.plot.setXRange(0, 12, padding=0)
        self.plot.setYRange(-min_span / 2, min_span / 2, padding=0)
        self.curves = [self.plot.plot(pen=pg.mkPen(c, width=2), connect="finite")
                       for c in AXIS_COLORS]
        layout.addWidget(self.plot, 1)

    def update_signal(self, times, values):
        for index, (curve, readout) in enumerate(zip(self.curves, self.values)):
            curve.setData(times, values[:, index])
            readout.setText(f"{values[-1, index]:+.{self.precision}f}")
        right = max(12.0, float(times[-1]))
        self.plot.setXRange(right - 12, right, padding=0)
        low, high = float(np.min(values)), float(np.max(values))
        middle = (low + high) / 2
        span = max(self.min_span, (high - low) * 1.25)
        self.plot.setYRange(middle - span / 2, middle + span / 2, padding=0)

    def clear_signal(self):
        for curve, value in zip(self.curves, self.values):
            curve.setData([], [])
            value.setText("—")
        self.plot.setXRange(0, 12, padding=0)


class Visualizer(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.stats = StreamStats()
        self.attitude = AttitudeEstimator()
        self.samples = deque(maxlen=2400)
        self.arrivals = deque(maxlen=2400)
        self.last_received = None
        self.rejected = 0
        self.connected = False
        self.notifications = 0
        self.mtu_size = None
        self.manual_stop = False
        self.closing = False
        self.stream_task = None
        self.stop_event = None
        self.output = None
        self.writer = None
        self.csv_path = None
        self.snapshot_saved = False
        self.dirty = False
        self.message = "보드를 찾는 중입니다."

        self.setWindowTitle("ISP_IMU — 실시간 센서 시각화")
        self.setMinimumSize(1080, 730)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1440, available.width() - 40), min(860, available.height() - 40))
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(25, 20, 25, 20)
        brand = label("IMU", "brand")
        brand.setAlignment(Qt.AlignCenter)
        brand.setFixedSize(49, 49)
        header_layout.addWidget(brand)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(label("IMU 신호", "title"))
        heading.addWidget(label("가속도 · 각속도 · 3D 자세 · 실시간 BLE", "subtitle"))
        header_layout.addLayout(heading)
        header_layout.addStretch()
        self.status = label("●  검색 중")
        self.status.setMinimumWidth(150)
        self.status.setStyleSheet("color: #68798b; font-size: 14px; font-weight: 600;")
        header_layout.addWidget(self.status)
        self.action = QPushButton("연결 취소")
        self.action.clicked.connect(self.toggle_connection)
        header_layout.addWidget(self.action)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(23, 20, 23, 14)
        body.setSpacing(18)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(170)
        metrics = QVBoxLayout(rail)
        metrics.setContentsMargins(21, 23, 21, 22)
        metrics.setSpacing(8)
        metrics.addWidget(label("수신 상태", "railTitle"))
        metrics.addSpacing(13)
        self.metric_labels = {}
        for key, title, unit in [
            ("rate", "실제 수신률", "Hz"),
            ("count", "받은 측정값", "개"),
            ("missing", "누락 측정값", "개"),
            ("age", "마지막 수신", "초 전"),
        ]:
            metrics.addWidget(label(title, "railCaption"))
            value = label("—" if key in ("rate", "age") else "0", "metric")
            metrics.addWidget(value)
            metrics.addWidget(label(unit, "metricUnit"))
            self.metric_labels[key] = value
            if key != "age":
                metrics.addSpacing(7)
                divider = QFrame()
                divider.setObjectName("railDivider")
                divider.setFixedHeight(1)
                metrics.addWidget(divider)
                metrics.addSpacing(8)
        metrics.addStretch()
        self.device_note = label("ISP_IMU\n연결 대기", "railCaption")
        self.device_note.setWordWrap(True)
        metrics.addWidget(self.device_note)
        body.addWidget(rail)
        plots = QVBoxLayout()
        plots.setSpacing(16)
        self.acceleration = SignalPanel("가속도", "g", 3, 2.4)
        self.gyroscope = SignalPanel("각속도", "°/s", 1, 10.0)
        plots.addWidget(self.acceleration, 1)
        plots.addWidget(self.gyroscope, 1)
        body.addLayout(plots, 3)
        self.orientation = OrientationPanel(self.attitude)
        body.addWidget(self.orientation, 1)
        outer.addLayout(body, 1)

        self.footer = label("실제 센서 데이터 대기 중", "footer")
        self.footer.setWordWrap(True)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(25, 0, 25, 13)
        footer_layout.addWidget(self.footer)
        outer.addLayout(footer_layout)
        self.setStyleSheet(STYLE)
        self.timer = QTimer(self)
        self.timer.setInterval(40)  # 25 fps display, independently of acquisition.
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def toggle_connection(self):
        if self.stream_task and not self.stream_task.done():
            self.manual_stop = True
            self.stream_task.cancel()
        else:
            self.start_stream()

    def start_stream(self):
        self.stats = StreamStats()
        self.attitude = AttitudeEstimator()
        self.orientation.estimator = self.attitude
        self.orientation.refresh()
        self.samples.clear()
        self.arrivals.clear()
        self.last_received = None
        self.rejected = 0
        self.manual_stop = False
        self.notifications = 0
        self.mtu_size = None
        self.connected = False
        self.stop_event = asyncio.Event()
        self.snapshot_saved = False
        self.acceleration.clear_signal()
        self.gyroscope.clear_signal()
        self.set_status("검색 중", "#68798b")
        self.device_note.setText("ISP_IMU\n연결 대기")
        self.footer.setText("보드 전원을 확인하세요. 실제 BLE 장치를 검색하고 있습니다.")
        self.action.setText("연결 취소")
        self.stream_task = asyncio.create_task(self.stream())

    def set_status(self, text, color):
        self.status.setText("●  " + text)
        self.status.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 600;")

    def on_packet(self, _characteristic, data):
        try:
            samples = decode_notification(data)
        except ValueError as error:
            self.rejected += 1
            self.message = f"수신 패킷 오류: {error}"
            print(self.message, flush=True)
            return
        now = time.monotonic()
        received_unix = time.time()
        self.notifications += 1
        self.last_received = now
        accepted = 0
        for sample in samples:
            try:
                elapsed = self.stats.observe(sample)
            except ValueError as error:
                self.rejected += 1
                self.message = f"수신 샘플 오류: {error}"
                print(self.message, flush=True)
                continue
            accepted += 1
            self.samples.append((elapsed, sample.ax_g, sample.ay_g, sample.az_g,
                                 sample.gx_dps, sample.gy_dps, sample.gz_dps))
            self.attitude.update(sample, elapsed)
            while self.samples and self.samples[0][0] < elapsed - 12:
                self.samples.popleft()
            if self.writer:
                self.writer.writerow([sample.seq, sample.device_ms, f"{elapsed:.3f}",
                                      f"{received_unix:.6f}", sample.ax_g, sample.ay_g, sample.az_g,
                                      sample.gx_dps, sample.gy_dps, sample.gz_dps])
        if accepted:
            self.arrivals.append((now, accepted))
        self.dirty = True

    async def stream(self):
        def disconnected(_client):
            self.connected = False
            if not self.manual_stop:
                self.message = "BLE 연결이 끊겼습니다. 보드 전원을 확인하고 다시 연결하세요."
            self.stop_event.set()

        try:
            print("GUI: scanning for real ISP_IMU BLE notifications", flush=True)
            devices = await scan_imu_devices(timeout=15)
            if not devices:
                raise RuntimeError("보드를 찾지 못했습니다. 전원을 확인하고 다시 연결하세요.")
            if self.args.device:
                selected = choose_device(devices, self.args.device)
                if selected is None:
                    raise RuntimeError(f"지정한 보드 {self.args.device}을 찾지 못했습니다. "
                                       "python scan_imu.py로 식별자를 확인하세요.")
            elif len(devices) == 1:
                selected = devices[0]
            else:
                self.set_status("보드 선택", "#68798b")
                choices = [f"{name}  [{device.address}]" for device, name in devices]
                choice, accepted = QInputDialog.getItem(
                    self, "IMU 보드 선택", "연결할 본인 보드를 고르세요:", choices, 0, False)
                if not accepted:
                    self.manual_stop = True
                    raise RuntimeError("보드 선택을 취소했습니다.")
                selected = devices[choices.index(choice)]
            device, device_name = selected
            self.set_status("연결 중", "#68798b")
            async with BleakClient(device, disconnected_callback=disconnected) as client:
                if client.mtu_size < 103:
                    raise RuntimeError("100Hz 수신에는 BLE MTU 103 이상이 필요합니다.")
                self.mtu_size = client.mtu_size
                self.connected = True
                self.csv_path = PROJECT_DIR / "data" / f"visual-{datetime.now():%Y%m%d-%H%M%S-%f}.csv"
                self.csv_path.parent.mkdir(parents=True, exist_ok=True)
                self.output = self.csv_path.open("w", newline="", encoding="utf-8")
                self.writer = csv.writer(self.output)
                self.writer.writerow(CSV_FIELDS)
                self.action.setText("수신 종료")
                self.device_note.setText(f"{device_name}\n가속도 · 각속도 6축")
                self.message = ""
                await client.start_notify(DATA_UUID, self.on_packet)
                print(f"GUI: connected to {device_name} [{device.address}]; "
                      f"live samples in BLE batches; ATT MTU={client.mtu_size}", flush=True)
                if self.args.check_seconds:
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), self.args.check_seconds)
                    except asyncio.TimeoutError:
                        self.manual_stop = True
                        self.message = "시각화 시험 완료"
                else:
                    await self.stop_event.wait()
                if client.is_connected:
                    await client.stop_notify(DATA_UUID)
        except asyncio.CancelledError:
            self.message = "수신을 종료했습니다. 그래프는 마지막 측정값을 표시합니다."
        except Exception as error:
            self.message = str(error)
            print(f"GUI connection error: {error}", flush=True)
        finally:
            self.connected = False
            if self.output:
                self.output.close()
            self.output = None
            self.writer = None
            self.action.setText("다시 연결")
            self.set_status("수신 종료" if self.manual_stop else "연결 끊김", "#68798b" if self.manual_stop else "#b45309")
            self.footer.setText(self.message or "수신을 종료했습니다.")
            print(f"GUI result: count={self.stats.count}, missing={self.stats.missing}, "
                  f"rejected={self.rejected}, board_rate_hz={self.stats.rate_hz:.2f}", flush=True)
            if self.closing:
                QTimer.singleShot(0, self.close)

    def refresh(self):
        now = time.monotonic()
        while self.arrivals and self.arrivals[0][0] < now - 2:
            self.arrivals.popleft()
        rate = None
        if len(self.arrivals) > 1 and self.connected:
            span = self.arrivals[-1][0] - self.arrivals[0][0]
            if span > 0:
                # The first batch precedes this interval; count subsequent
                # samples, so batching does not inflate the displayed rate.
                rate = (sum(count for _, count in self.arrivals) - self.arrivals[0][1]) / span
        self.metric_labels["rate"].setText(f"{rate:.1f}" if rate is not None else "—")
        self.metric_labels["count"].setText(f"{self.stats.count:,}")
        self.metric_labels["missing"].setText(f"{self.stats.missing:,}")
        age = now - self.last_received if self.last_received is not None else None
        self.metric_labels["age"].setText(f"{age:.1f}" if age is not None else "—")
        self.orientation.refresh(stale=not self.connected or age is None or age >= 1.5)
        if self.connected:
            if self.rejected:
                self.set_status("데이터 오류", "#b45309")
            elif age is not None and age < 1.5:
                self.set_status("수신 중", "#047857")
            else:
                self.set_status("데이터 대기", "#b45309")
            if self.output:
                self.output.flush()
            self.footer.setText(
                f"CSV 기록 중  ·  {self.csv_path.name}  ·  해석 오류 {self.rejected}개"
                if self.csv_path else "실제 센서 데이터 대기 중"
            )
        if self.dirty and self.samples:
            values = np.asarray(self.samples)
            self.acceleration.update_signal(values[:, 0], values[:, 1:4])
            self.gyroscope.update_signal(values[:, 0], values[:, 4:7])
            self.dirty = False
        if self.args.snapshot and not self.snapshot_saved and self.samples and self.samples[-1][0] >= 5:
            self.args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot_image = self.grab().toImage()
            evidence = {
                    "source": "real BLE notifications", "count": self.stats.count,
                    "missing": self.stats.missing, "rejected": self.rejected,
                    "board_rate_hz": self.stats.rate_hz,
                    "notifications": self.notifications, "att_mtu": self.mtu_size,
                    "csv": str(self.csv_path), "latest": list(self.samples[-1]),
                    "visible_curves": sum(len(curve.getData()[0]) > 0
                                          for panel in (self.acceleration, self.gyroscope)
                                          for curve in panel.curves),
                    "orientation": {
                        "source": "six-axis BLE measurements, gravity/gyro fusion",
                        "ready": self.attitude.ready,
                        "updates": self.attitude.updates,
                        "roll_pitch_yaw_degrees": self.attitude.angles_degrees,
                        "board_to_world_matrix": self.attitude.matrix.tolist(),
                        "quaternion_wxyz": self.attitude.quaternion.tolist(),
                        "gyro_bias_board_uvz_dps": self.attitude.bias_dps.tolist(),
                        "calibrating": self.attitude.calibrating,
                        "paint_count": self.orientation.view.paint_count,
                    },
            }
            self.snapshot_saved = True
            # PNG encoding is slow on Retina captures. Keep it off the BLE/Qt
            # event loop so taking verification evidence cannot pause reception.
            self.snapshot_task = asyncio.create_task(self.save_snapshot(snapshot_image, evidence))

    async def save_snapshot(self, snapshot_image, evidence):
        try:
            saved = await asyncio.to_thread(snapshot_image.save, str(self.args.snapshot))
            if saved:
                self.args.snapshot.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n")
                print(f"GUI snapshot saved: {self.args.snapshot}", flush=True)
            else:
                print("GUI snapshot failed", flush=True)
        except Exception as error:
            print(f"GUI snapshot failed: {error}", flush=True)

    def closeEvent(self, event):
        if self.stream_task and not self.stream_task.done():
            event.ignore()
            self.closing = True
            self.manual_stop = True
            self.stream_task.cancel()
        else:
            self.timer.stop()
            event.accept()


def main():
    parser = argparse.ArgumentParser(description="실제 IMU BLE 데이터 실시간 시각화")
    parser.add_argument("--device", help="scan_imu.py에 표시되는 보드 식별자(Mac UUID 또는 Windows 주소)")
    parser.add_argument("--snapshot", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--check-seconds", type=float, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    prepare_qt_platform()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ISP_IMU")
    app.setFont(QFont("Malgun Gothic" if sys.platform == "win32" else "Apple SD Gothic Neo", 11))
    pg.setConfigOptions(antialias=True, foreground="#607187")
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = Visualizer(args)
    for termination_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(termination_signal, lambda _signum, _frame: QTimer.singleShot(0, window.close))
    window.show()
    window.raise_()
    window.activateWindow()
    QTimer.singleShot(100, window.start_stream)
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
