#!/bin/bash
set -euo pipefail
imu_project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$imu_project_dir"
if [[ ! -x .venv/bin/python ]]; then
  echo '프로젝트 Python 환경이 필요합니다. README의 준비 절차를 먼저 실행하세요.' >&2
  exit 1
fi
exec .venv/bin/python visualize_imu.py "$@"
