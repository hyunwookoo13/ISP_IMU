#!/usr/bin/env python3
"""Receive real BLE measurements. No synthetic data or demo fallback."""
import argparse
import asyncio
import csv
import sys
import time
from pathlib import Path

from bleak import BleakClient
from bleak.exc import BleakError

from imu_protocol import DATA_UUID, DEVICE_NAME, StreamStats, decode_notification
from imu_discovery import choose_device, scan_imu_devices

CSV_FIELDS = ["seq", "device_ms", "device_time_s", "received_unix_s",
              "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps"]


async def receive(args: argparse.Namespace) -> int:
    print(f"BLE 검색: {DEVICE_NAME} (최대 {args.timeout:g}초)", flush=True)
    devices = await scan_imu_devices(timeout=args.timeout)
    if not devices:
        print("보드를 찾지 못했습니다. 전원, BLE 프로그램 업로드, Bluetooth 권한을 확인하세요.", file=sys.stderr)
        return 1
    if args.device:
        selected = choose_device(devices, args.device)
        if selected is None:
            print(f"지정한 보드 {args.device}을 찾지 못했습니다. python scan_imu.py로 확인하세요.", file=sys.stderr)
            return 1
    elif len(devices) == 1:
        selected = devices[0]
    else:
        print("여러 ISP_IMU 보드가 보입니다. 본인 보드 주소를 --device로 지정하세요:", file=sys.stderr)
        for found_device, name in devices:
            print(f"  {name}  {found_device.address}", file=sys.stderr)
        return 1
    device, device_name = selected

    print(f"발견: {device_name} / {device.address}", flush=True)
    disconnected = asyncio.Event()
    stats = StreamStats()
    rejected = 0
    last_print = 0.0
    first_received = None
    last_received = None
    output = None
    writer = None
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        output = args.csv.open("w", newline="", encoding="utf-8")
        writer = csv.writer(output)
        writer.writerow(CSV_FIELDS)

    def notification(_characteristic, data: bytearray) -> None:
        nonlocal rejected
        try:
            samples = decode_notification(data)
        except ValueError as error:
            rejected += 1
            print(f"수신 패킷 오류: {error}", file=sys.stderr, flush=True)
            return
        received_unix = time.time()
        for sample in samples:
            observe_sample(sample, received_unix)

    def observe_sample(sample, received_unix):
        nonlocal rejected, last_print, first_received, last_received
        try:
            elapsed = stats.observe(sample)
        except ValueError as error:
            rejected += 1
            if rejected == 1:
                print(f"수신 패킷 오류: {error}", file=sys.stderr, flush=True)
            return
        now = time.monotonic()
        if first_received is None:
            first_received = now
        last_received = now
        if writer:
            writer.writerow([sample.seq, sample.device_ms, f"{elapsed:.3f}",
                             f"{received_unix:.6f}", sample.ax_g, sample.ay_g, sample.az_g,
                             sample.gx_dps, sample.gy_dps, sample.gz_dps])
        if now - last_print >= 1:
            last_print = now
            print(
                f"seq={sample.seq:>8}  t={elapsed:7.3f}s  "
                f"accel[g]=({sample.ax_g:+.3f}, {sample.ay_g:+.3f}, {sample.az_g:+.3f})  "
                f"gyro[deg/s]=({sample.gx_dps:+.1f}, {sample.gy_dps:+.1f}, {sample.gz_dps:+.1f})  "
                f"수신={stats.count} 누락={stats.missing}", flush=True,
            )
            if output:
                output.flush()

    unexpected_disconnect = False
    try:
        async with BleakClient(device, disconnected_callback=lambda _client: disconnected.set()) as client:
            if client.mtu_size < 103:
                raise ValueError("100Hz 수신에는 BLE MTU 103 이상이 필요합니다")
            print(f"협상된 ATT MTU: {client.mtu_size}", flush=True)
            await client.start_notify(DATA_UUID, notification)
            print("연결됨. 가속도[g] / 각속도[deg/s] 수신 중. Ctrl+C로 종료.", flush=True)
            if args.duration:
                try:
                    await asyncio.wait_for(disconnected.wait(), timeout=args.duration)
                    unexpected_disconnect = True
                except asyncio.TimeoutError:
                    pass
            else:
                await disconnected.wait()
                unexpected_disconnect = True
            if client.is_connected:
                await client.stop_notify(DATA_UUID)
    finally:
        if output:
            output.close()
        arrival_hz = 0.0
        if stats.count > 1 and last_received > first_received:
            arrival_hz = (stats.count - 1) / (last_received - first_received)
        print(f"결과: 유효 측정값 {stats.count}, 누락 {stats.missing}, 오류 {rejected}, "
              f"보드 시간 기준 {stats.rate_hz:.1f}Hz, PC 수신 기준 {arrival_hz:.1f}Hz", flush=True)
        if args.csv:
            print(f"CSV: {args.csv.resolve()}", flush=True)
    if unexpected_disconnect:
        print("시험 중 BLE 연결이 끊겼습니다.", file=sys.stderr)
        return 1
    if stats.count < 2 or rejected or stats.missing:
        print("수신 확인 실패: 오류와 순번 누락이 없는 연속 IMU 데이터가 필요합니다.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ISP_IMU 보드의 실제 BLE IMU 값 수신 확인")
    parser.add_argument("--duration", type=float, default=10, help="수신 시간(초), 0이면 계속 수신. 기본 10")
    parser.add_argument("--timeout", type=float, default=15, help="BLE 검색 시간(초). 기본 15")
    parser.add_argument("--csv", type=Path, help="원본 측정값을 저장할 CSV 경로")
    parser.add_argument("--device", help="scan_imu.py에 표시되는 보드 식별자(Mac UUID 또는 Windows 주소)")
    args = parser.parse_args()
    if args.duration < 0 or args.timeout <= 0:
        parser.error("duration은 0 이상, timeout은 0보다 커야 합니다")
    try:
        return asyncio.run(receive(args))
    except KeyboardInterrupt:
        return 130
    except (BleakError, OSError, ValueError) as error:
        print(f"수신 실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
