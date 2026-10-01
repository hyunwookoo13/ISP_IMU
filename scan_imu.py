#!/usr/bin/env python3
"""List nearby ISP_IMU boards and their Mac/Windows BLE identifiers."""

import argparse
import asyncio

from imu_discovery import scan_imu_devices


async def main(timeout):
    devices = await scan_imu_devices(timeout=timeout)
    if not devices:
        print("ISP_IMU 보드를 찾지 못했습니다. 보드 전원과 Bluetooth 권한을 확인하세요.")
        return 1
    for device, name in devices:
        print(f"{name}  {device.address}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.timeout)))
