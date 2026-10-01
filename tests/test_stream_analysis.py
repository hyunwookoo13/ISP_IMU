"""Independent timing fixtures for the CSV rate checker, not live sensor data."""
import csv
import tempfile
import unittest
from pathlib import Path

from receive_imu import CSV_FIELDS
from scripts.analyze_stream import analyze


class StreamAnalysisTests(unittest.TestCase):
    def fixture(self, dropped_index=None, burst=False):
        rows = []
        for index in range(301):
            if index == dropped_index:
                continue
            arrival = 1000+(index//3)*.03 if burst else 1000+index*.01
            rows.append([(0xfffffff0+index) & 0xffffffff,
                         (0xffffffc4+index*10) & 0xffffffff, index*.01, arrival,
                         0, 0, 1, 0, 0, 0])
        return rows

    def check(self, rows, minimum=2):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"timing-fixture.csv"
            with path.open("w", newline="") as source:
                writer = csv.writer(source)
                writer.writerow(CSV_FIELDS)
                writer.writerows(rows)
            return analyze(path, 100, minimum)

    def test_100_hz_with_sequence_and_timestamp_wrap(self):
        result = self.check(self.fixture())
        self.assertTrue(result["passed"])
        self.assertEqual(result["board_rate_hz"], 100)
        self.assertEqual(result["board_read_spacing_ms"]["min"], 10)
        self.assertEqual(result["board_read_spacing_ms"]["max"], 10)

    def test_arrival_bursts_do_not_change_sensor_rate_check(self):
        result = self.check(self.fixture(burst=True))
        self.assertTrue(result["passed"])
        self.assertEqual(result["arrival_spacing_ms"]["min"], 0)
        self.assertGreater(result["arrival_spacing_ms"]["max"], 29)

    def test_packet_loss_fails_despite_an_average_near_100_hz(self):
        result = self.check(self.fixture(dropped_index=150))
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks"]["board_rate"])
        self.assertEqual(result["sequence_gaps"], 1)
        self.assertFalse(result["checks"]["read_spacing"])

    def test_short_capture_cannot_pass_a_long_duration_requirement(self):
        result = self.check(self.fixture(), minimum=30)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["duration"])
