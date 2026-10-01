#!/usr/bin/env python3
"""Install, build, and upload the Nano 33 BLE Rev2 firmware on macOS or Windows."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "firmware" / "imu_ble"
BUILD = ROOT / ".build"
FQBN = "arduino:mbed_nano:nano33ble"
CORE = "arduino:mbed_nano@4.6.0"
LIBRARIES = ("ArduinoBLE@2.0.2", "Arduino_BMI270_BMM150@1.2.3")


def find_cli():
    specified = os.environ.get("IMU_ARDUINO_CLI")
    if specified:
        found = shutil.which(specified)
        if found:
            return found
        raise RuntimeError("IMU_ARDUINO_CLI 경로에서 Arduino CLI를 찾지 못했습니다: " + specified)
    found = shutil.which("arduino-cli")
    if found:
        return found
    if sys.platform == "darwin":
        bundled = Path("/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli")
        if bundled.is_file():
            return str(bundled)
    raise RuntimeError("Arduino CLI를 설치해 PATH에 추가하거나 IMU_ARDUINO_CLI을 설정하세요: "
                       "https://docs.arduino.cc/arduino-cli/installation/")


def matching_ports(board_list):
    """Return only USB ports recognized as this project's board."""
    ports = []
    for item in board_list.get("detected_ports", []):
        if any(board.get("fqbn") == FQBN for board in item.get("matching_boards", [])):
            address = item.get("port", {}).get("address")
            if address:
                ports.append(address)
    return ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="업로드 포트를 직접 지정합니다. 예: COM3 또는 /dev/cu.usbmodem1101")
    parser.add_argument("--build-only", action="store_true", help="컴파일까지만 진행합니다. 보드 연결은 불필요합니다.")
    parser.add_argument("--skip-install", action="store_true", help="이미 설치된 Arduino 코어·라이브러리를 사용합니다.")
    args = parser.parse_args()
    try:
        cli = find_cli()

        def run(*arguments, capture=False):
            command = [cli, *arguments]
            print("Arduino CLI:", " ".join(arguments), flush=True)
            return subprocess.run(command, cwd=str(ROOT), check=True, text=True,
                                  stdout=subprocess.PIPE if capture else None)

        if not args.skip_install:
            run("core", "update-index")
            run("core", "install", CORE)
            run("lib", "install", *LIBRARIES)

        BUILD.mkdir(parents=True, exist_ok=True)
        run("compile", "--fqbn", FQBN, "--build-path", str(BUILD), str(SKETCH))
        if args.build_only:
            print("빌드 완료. USB로 보드를 연결한 뒤 --build-only 없이 다시 실행하세요.")
            return 0

        port = args.port
        if not port:
            ports = matching_ports(json.loads(run("board", "list", "--format", "json", capture=True).stdout))
            if not ports:
                raise RuntimeError("Nano 33 BLE Rev2 USB 포트를 찾지 못했습니다. 데이터 케이블로 "
                                   "보드를 연결하고 다시 실행하세요. 필요하면 --port를 지정하세요.")
            if len(ports) > 1:
                raise RuntimeError("보드가 여러 개 연결돼 있습니다: " + ", ".join(ports) +
                                   ". 사용할 보드를 --port로 지정하세요.")
            port = ports[0]
        run("upload", "--fqbn", FQBN, "--input-dir", str(BUILD), "--port", port, str(SKETCH))
        print("업로드 완료. USB를 전원용으로 유지하거나 보조배터리로 옮긴 뒤 시각화 앱을 실행하세요.")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("보드 준비 실패:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
