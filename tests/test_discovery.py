import unittest
from types import SimpleNamespace

from imu_discovery import choose_device, is_imu_advertisement
from imu_protocol import SERVICE_UUID


class DiscoveryTests(unittest.TestCase):
    def test_legacy_and_unique_board_names_are_found(self):
        device = SimpleNamespace(name=None, address="AA:BB:CC:DD:EE:FF")
        for name in ("ISP_IMU", "ISP_IMU_A1B2C3"):
            with self.subTest(name=name):
                adv = SimpleNamespace(local_name=name, service_uuids=[])
                self.assertTrue(is_imu_advertisement(device, adv))

    def test_service_uuid_recovers_a_missing_scan_response_name(self):
        device = SimpleNamespace(name=None, address="AA:BB:CC:DD:EE:FF")
        adv = SimpleNamespace(local_name=None, service_uuids=[SERVICE_UUID.upper()])
        self.assertTrue(is_imu_advertisement(device, adv))

    def test_other_devices_are_not_selected(self):
        device = SimpleNamespace(name="Unknown", address="AA:BB:CC:DD:EE:FF")
        adv = SimpleNamespace(local_name="ISP_IMU_Wrong", service_uuids=[])
        self.assertFalse(is_imu_advertisement(device, adv))

    def test_identifier_selection_is_case_insensitive(self):
        device = SimpleNamespace(name="ISP_IMU_A1B2C3", address="D1BA4BFF-4DD6-D449-6067-05BBBD73C1A2")
        self.assertEqual(choose_device([(device, device.name)], device.address.lower()), (device, device.name))


if __name__ == "__main__":
    unittest.main()
