"""Find this project's BLE boards without confusing classmates' devices."""

import asyncio
import re

from bleak import BleakScanner

from imu_protocol import DEVICE_NAME, SERVICE_UUID


def is_imu_advertisement(device, advertisement):
    name = advertisement.local_name or device.name or ""
    services = advertisement.service_uuids or []
    return (name == DEVICE_NAME or re.fullmatch(r"ISP_IMU_[0-9A-Fa-f]{6}", name) is not None
            or any(service.lower() == SERVICE_UUID for service in services))


async def scan_imu_devices(timeout=15, settle=3):
    """After the first match, listen briefly for other boards in the room."""
    matches = {}
    first_seen = asyncio.Event()

    def record(device, advertisement):
        if is_imu_advertisement(device, advertisement):
            name = advertisement.local_name or device.name or DEVICE_NAME
            matches[device.address.casefold()] = (device, name)
            first_seen.set()

    scanner = BleakScanner(detection_callback=record)
    async with scanner:
        try:
            await asyncio.wait_for(first_seen.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return []
        await asyncio.sleep(settle)
    return sorted(matches.values(), key=lambda entry: (entry[1], entry[0].address))


def choose_device(devices, address):
    for device, name in devices:
        if device.address.casefold() == address.casefold():
            return device, name
    return None
