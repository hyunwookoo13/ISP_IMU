import unittest

from imu_protocol import Sample, StreamStats, decode_packet, decode_notification


class ProtocolTests(unittest.TestCase):
    def test_wire_example_units_and_signed_values(self):
        # Independently written wire bytes: seq=1, ms=20, accel=(1,-1,0) g,
        # gyro=(10,-10,0) deg/s. This is a protocol fixture, not sensor data.
        wire = bytes.fromhex("01000000 14000000 e803 18fc 0000 6400 9cff 0000")
        self.assertEqual(decode_packet(wire), Sample(1, 20, 1, -1, 0, 10, -10, 0))

    def test_rejects_incomplete_packet(self):
        with self.assertRaises(ValueError):
            decode_packet(bytes(19))

    def test_batch_keeps_sample_order_timestamps_units_and_wrap(self):
        first = bytes.fromhex("ffffffff f7ffffff e803 18fc 0000 6400 9cff 0000")
        second = bytes.fromhex("00000000 01000000 18fc e803 0000 9cff 6400 0000")
        a, b = decode_notification(first+second)
        self.assertEqual(a, Sample(0xffffffff,0xfffffff7,1,-1,0,10,-10,0))
        self.assertEqual(b, Sample(0,1,-1,1,0,-10,10,0))
        self.assertEqual(decode_notification(second), (b,))
        self.assertEqual(len(decode_notification(second*5)), 5)
        stats = StreamStats()
        stats.observe(a)
        self.assertAlmostEqual(stats.observe(b), .010)

    def test_batch_rejects_empty_partial_and_oversized_notifications(self):
        for length in (0, 19, 21, 39, 101, 120):
            with self.subTest(length=length), self.assertRaises(ValueError):
                decode_notification(bytes(length))

    def test_wrap_and_lost_sequence(self):
        stats = StreamStats()
        stats.observe(Sample(0xFFFFFFFE, 0xFFFFFFF0, 0, 0, 1, 0, 0, 0))
        elapsed = stats.observe(Sample(1, 44, 0, 0, 1, 0, 0, 0))
        self.assertAlmostEqual(elapsed, 0.060)
        self.assertEqual(stats.missing, 2)

    def test_rejects_board_restart_or_duplicate(self):
        for seq, ms in [(10, 100), (0, 0)]:
            stats = StreamStats()
            stats.observe(Sample(10, 100, 0, 0, 1, 0, 0, 0))
            with self.assertRaises(ValueError):
                stats.observe(Sample(seq, ms, 0, 0, 1, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
