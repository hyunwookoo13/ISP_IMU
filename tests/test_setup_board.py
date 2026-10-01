import unittest

from scripts.setup_board import FQBN, matching_ports


class BoardSelectionTests(unittest.TestCase):
    def test_selects_target_board_without_guessing_other_serial_ports(self):
        board_list = {"detected_ports": [
            {"port": {"address": "COM1"}},
            {"port": {"address": "COM4"}, "matching_boards": [{"fqbn": "arduino:avr:uno"}]},
            {"port": {"address": "COM7"}, "matching_boards": [{"fqbn": FQBN}]},
        ]}
        self.assertEqual(matching_ports(board_list), ["COM7"])

    def test_preserves_multiple_matching_ports_for_explicit_selection(self):
        board_list = {"detected_ports": [
            {"port": {"address": "COM7"}, "matching_boards": [{"fqbn": FQBN}]},
            {"port": {"address": "/dev/cu.usbmodem1101"}, "matching_boards": [{"fqbn": FQBN}]},
        ]}
        self.assertEqual(matching_ports(board_list), ["COM7", "/dev/cu.usbmodem1101"])


if __name__ == "__main__":
    unittest.main()
