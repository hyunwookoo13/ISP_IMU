#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${IMU_ARDUINO_CLI:-}" ]]; then
  exec "$IMU_ARDUINO_CLI" "$@"
fi
if command -v arduino-cli >/dev/null 2>&1; then
  exec arduino-cli "$@"
fi
imu_bundled_cli='/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli'
if [[ -x "$imu_bundled_cli" ]]; then
  exec "$imu_bundled_cli" "$@"
fi
echo 'Arduino CLI가 필요합니다. 설치하거나 IMU_ARDUINO_CLI에 실행 파일 경로를 지정하세요.' >&2
exit 1
