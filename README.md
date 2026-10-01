# ISP_IMU — BLE 수신 확인

Arduino Nano 33 BLE **Rev2**의 가속도 3축과 각속도 3축을 BLE로 받아 **실시간 그래프와 3D 자세**에서 확인하는 프로젝트입니다.
3D 자세는 실제 측정값으로 계산한 추정치이며, 그래프와 CSV에는 센서 값을 그대로 표시·저장합니다. 분류 모델은 포함하지 않습니다.

이 배포본은 **학생 모두 같은 Nano 33 BLE Rev2와 내장 BMI270**을 사용하는 수업 기준입니다. USB로 처음 한 번 업로드한 뒤 맥 또는 Windows PC가 BLE로 값을 받습니다. 다른 종류의 보드나 IMU 칩을 쓰면 센서 드라이버, 축 방향과 단위, 보드용 코어를 변경하고 재검증해야 합니다.
맥에서는 실제 보드와 BLE 수신까지 확인했습니다. Windows는 설치·빌드·코드 검사를 자동화했으며, Windows PC와 보드 사이의 실제 BLE 연결 시험은 아직 필요합니다.

실제 하드웨어 수신 결과는 [VERIFICATION.md](VERIFICATION.md)에 기록합니다.

## 공통 준비

- 보드: Nano 33 BLE Rev2 (BMI270/BMM150), 데이터 전송 가능한 Micro-USB 케이블.
- PC: Bluetooth가 있는 맥 또는 Windows PC, Python 3.9–3.12 (Windows에서는 3.11 권장), [Arduino CLI](https://docs.arduino.cc/arduino-cli/installation/).
- 보드용 코어: `arduino:mbed_nano@4.6.0`.

Arduino CLI가 `PATH`에 있으면 준비 스크립트가 찾아 사용합니다. 이 맥에서는 설치된 Arduino IDE의 CLI도 찾을 수 있습니다. Windows에서는 Arduino CLI를 설치하고 `arduino-cli` 명령이 PowerShell에서 실행되도록 `PATH`에 추가합니다.

## 맥에서 처음 설치·업로드

프로젝트 폴더에서 실행합니다. 보드를 **맥 USB에 연결한 상태**에서 마지막 준비 명령을 실행하세요.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/setup_board.py
.venv/bin/python visualize_imu.py
```

## Windows에서 처음 설치·업로드

PowerShell에서 프로젝트 폴더로 이동해 실행합니다. 보드를 **Windows PC USB에 연결한 상태**에서 준비 명령을 실행하세요.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\setup_board.py
.\start_visualizer.bat
```

`setup_board.py`는 고정된 코어·라이브러리 버전을 설치하고, 펌웨어를 빌드한 다음, 연결된 Nano 33 BLE Rev2 포트를 찾아 업로드합니다. 여러 보드가 연결됐거나 자동 탐지가 되지 않으면 `--port COM3` 또는 `--port /dev/cu.usbmodem1101`처럼 포트를 지정하세요. 포트는 `arduino-cli board list`에서 확인합니다. 보드 없이 빌드만 하려면 `--build-only`, 필요한 코어·라이브러리가 이미 설치돼 있으면 `--skip-install`을 사용할 수 있습니다.

보드는 BLE 주소의 마지막 6자리로 만든 `ISP_IMU_XXXXXX`라는 고유한 이름으로 광고합니다. 이전 펌웨어의 `ISP_IMU` 이름도 수신 프로그램에서 찾을 수 있습니다. `while (!Serial)`을 사용하지 않아 보조배터리 전원에서도 시작됩니다.
업로드 후 USB는 전원 공급에만 사용해도 됩니다. 보조배터리로 전원을 바꾼 뒤 수신을 다시 시험합니다.
정상 초기화 후 내장 LED는 BLE 연결 중 켜집니다. 빠르게 반복 점멸하면 IMU 또는 BLE 초기화 오류입니다.

### 보조배터리 전원

이 보드는 소비전류가 작아 보조배터리의 자동 차단 대상이 될 수 있습니다. 실제 샤오미 보조배터리 시험에서도 약 25초 후 보드 전원이 꺼졌습니다.

사진의 샤오미 보조배터리에서는 버튼을 빠르게 두 번 눌러 **저전류 모드**를 켭니다. 보조배터리 LED가 순서대로 점멸하는지 확인한 뒤 시각화 창에서 `다시 연결`합니다. 동작이 다르면 해당 보조배터리 모델의 설명서를 확인합니다.
[샤오미 공식 FAQ](https://www.mi.com/my/support/faq/details/KA-300034/)에 따르면 이 모드는 2시간 후 해제되므로 수업·측정 전에 다시 켜서 확인합니다. 전원 케이블은 보조배터리에 연결하고, 맥북은 BLE로 데이터를 받습니다.

## 실시간 그래프 보기

맥에서는 Finder에서 **`start_visualizer.command`를 더블클릭**, Windows에서는 **`start_visualizer.bat`를 더블클릭**하면 시각화 창이 열리고 보드에 자동 연결됩니다. 준비 명령으로 Python 환경과 라이브러리를 설치한 후 사용합니다. 명령어로 실행할 수도 있습니다.

```sh
.venv/bin/python visualize_imu.py
```

- 가속도와 각속도 그래프에 X·Y·Z를 동일한 색상으로 구분해 표시합니다.
- 오른쪽 3D 패널에서 보드와 좌표축이 실제 BLE 측정값에 따라 회전합니다.
- 최근 12초를 보드 읽기 시간 기준으로 그립니다. 화면 갱신과 센서 획득은 독립적입니다.
- 실제 수신률, 누적 측정 수, 누락 측정값 수, 마지막 수신 시간을 표시합니다.
- 데이터가 1.5초 이상 오지 않으면 `데이터 대기`, 연결이 끊기면 `연결 끊김`을 표시합니다.
- `data/visual-날짜-시간.csv`에 세션별로 저장합니다. 기존 파일을 덮어쓰지 않습니다.
- `수신 종료`는 연결을 끊고 마지막 그래프를 유지합니다. `다시 연결`은 새 세션을 시작합니다.

주변에 수업용 보드가 여러 대 켜져 있으면 시각화 창이 **보드 선택 창**을 띄웁니다. 처음에는 본인 보드만 켠 상태에서 아래 명령으로 `ISP_IMU_XXXXXX` 이름을 확인하고 보드에 표시해 두면 이후 쉽게 고를 수 있습니다. 맥의 식별자는 CoreBluetooth UUID이고 Windows에서는 Bluetooth 주소이므로 두 PC에 보이는 식별자 문자열은 다를 수 있습니다.

```sh
.venv/bin/python scan_imu.py
.venv/bin/python visualize_imu.py --device <표시된-식별자>
```

Windows에서는 위 명령의 `.venv/bin/python`을 `.\.venv\Scripts\python.exe`로 바꿉니다. 한 대만 보이면 `--device` 없이 자동 연결됩니다. 다른 보드와 구분이 안 되면 그 보드의 전원만 켜고 다시 검색하세요.

보드를 기울이거나 회전해 그래프와 각 축 값이 변하는지 확인합니다.

### 100Hz 획득과 BLE 전송

- 가속도와 자이로를 100Hz로 설정하고 새 데이터가 준비됐을 때 함께 읽습니다. 내부 I²C 버스는 400kHz이며, 연속 읽기를 위해 BMI270의 advanced power save를 끕니다.
- 측정값 5개를 100바이트 BLE 알림 하나로 묶어 보냅니다. 측정은 초당 약 100회, 알림은 약 20회이며 각 측정값의 순번·읽기 시간을 보존합니다.
- 첫 측정값은 나머지 4개를 기다리므로 묶음 전송 자체에 최대 약 40ms의 대기 시간이 추가됩니다. BLE·맥북 처리 지연은 별도입니다.
- 이 전송 방식은 ATT MTU 103 이상이 필요합니다. 수신 프로그램은 연결 시 확인합니다. 이 맥북과 보드는 247로 협상했습니다. Windows Bluetooth 어댑터에서도 실제 연결 후 103 이상인지 확인해야 합니다.
- 화면은 초당 25회 갱신하지만, CSV 기록과 자세 계산은 수신한 모든 측정값을 사용합니다. 100Hz는 현재 설정 목표이며 시스템 전체의 최대 속도를 측정한 결과는 아닙니다.
- USB 진단 로그는 읽기를 지연시킬 수 있어 기본으로 끕니다. 진단용으로 필요할 때만 펌웨어의 `LOG_USB_DIAGNOSTICS`를 켜고 다시 빌드합니다.

### 실시간 3D 자세

- 연결 후 보드를 약 1초간 정지시키면 자이로 영점 보정이 완료됩니다. 움직이면 정지 구간을 다시 기다립니다.
- `정지 보정`은 현재 자세에서 자이로의 영점을 다시 측정합니다. `방향 0°`는 현재 수평 방향을 기준으로 설정하며 기울기를 유지합니다.
- Roll은 너비축(그래프 Y), Pitch는 길이축(그래프 X)의 회전입니다. Yaw는 기준 방향에 대한 수평 회전입니다.
- 부품면을 바라보고 USB를 아래에 둘 때, 그래프의 +X는 USB 반대쪽, +Y는 오른쪽, +Z는 부품면 바깥쪽입니다.
- 설치된 Arduino 라이브러리가 X·Y를 교환·반전하므로 자세 계산에서는 `u=Y, v=X, w=Z`인 오른손 좌표계로 가속도와 자이로를 함께 변환합니다. 그래프의 축과 전송 형식은 그대로입니다.
- `imu_orientation.py`는 쿼터니언 자이로 적분과 중력 방향 피드백을 결합합니다. BLE 도착 간격 대신 보드의 실제 측정 시간 간격을 사용합니다.
- 가속도 크기가 1g에서 크게 벗어나면 중력 보정의 비중을 줄입니다. 선형 가속도가 크면 기울기 추정에도 오차가 생길 수 있습니다.
- 자기장 값은 전송하지 않으므로 Yaw는 절대 방위가 아니며 오차가 누적될 수 있습니다. 3D 화면은 위치 이동을 추정하지 않습니다.
- Euler 각도는 ±90° Pitch 부근에서 표현이 달라질 수 있지만, 보드 렌더링은 쿼터니언을 사용하여 뒤집힘도 표시합니다.
- 데이터가 끊기면 마지막 자세를 유지하고 대기 상태를 표시합니다.

## 터미널 진단 수신

```sh
.venv/bin/python receive_imu.py --duration 35 --csv data/imu_100hz_check.csv
```

실제 BLE 알림을 받아 약 1초마다 가속도[g], 각속도[deg/s], 누적 수신 수와 누락 수를 표시합니다.
`--duration 0`이면 Ctrl+C까지 수신합니다. 실제 수신률은 실행 결과에 표시됩니다(현재 센서 설정: 100Hz).
`--csv`는 선택 사항이며 지정한 파일은 실행할 때 새로 씁니다. 계속 기록할 때는 파일명을 바꿔 주세요.

수신 기록에서 실제 속도, 순번 누락, 읽기 간격을 검사할 수 있습니다.

```sh
.venv/bin/python scripts/analyze_stream.py data/imu_100hz_check.csv --target-hz 100 --minimum-seconds 30
```

분석기의 엄격한 100Hz 시험은 30초 이상 기록, 보드·도착 시간 기준 속도 ±5%, 순번 누락 0, 읽기 간격 0초 초과·15ms 이하를 요구합니다. 실패하면 종료 코드 1을 반환합니다. 현재 하드웨어 시험에서는 약 99.5Hz로 누락 없이 수신됐지만 읽기 간격이 16ms까지 변해 간격 기준은 실패했습니다. 실제 결과는 `VERIFICATION.md`를 확인합니다. `receive_imu.py`는 해석 오류나 순번 누락이 있으면 수신 확인을 실패로 처리합니다.

Bluetooth 접근 허용 창이 나타나면 실행 중인 앱에 허용합니다. macOS의 **시스템 설정 → 개인정보 보호 및 보안 → Bluetooth**에서도 실행 앱의 권한을 확인할 수 있습니다.
Windows에서는 **설정 → Bluetooth 및 장치**에서 Bluetooth가 켜져 있는지 확인합니다.
보드 전원, 업로드, 앱 권한을 확인해도 찾지 못한다면 맥북 Bluetooth 상태를 확인합니다.

보드를 정지시키면 가속도 벡터 크기는 중력 때문에 대략 1g이고, 각속도는 대략 0deg/s입니다.
기울이거나 회전했을 때 축별 값이 변하는지 확인합니다. 축 방향에 따라 가속도의 부호는 달라집니다.
연결 및 패킷 수신 확인은 센서의 정확도 보정이나 파우치 착용 중 안정성을 보증하는 시험과 구분합니다.

## 전송 형식 v1

서비스 UUID: `9a407100-8c00-4b22-9f8d-13fbf859c8aa`

데이터 characteristic UUID: `9a407101-8c00-4b22-9f8d-13fbf859c8aa`

각 측정값은 **20바이트, little-endian**, Python `struct` 형식은 `<IIhhhhhh`입니다. 현재 펌웨어는 5개를 순서대로 이어 붙인 100바이트 알림을 보냅니다. Python 수신기는 기존 20바이트 알림과 1–5개 측정값의 묶음을 모두 해석합니다.

| 항목 | 형식 | 의미 |
| --- | --- | --- |
| seq | uint32 | 보드에서 읽은 측정값의 순번 |
| device_ms | uint32 | IMU를 읽은 직후의 보드 `millis()` 시간 |
| ax, ay, az | int16 각각 | 가속도, 1 LSB = 0.001g |
| gx, gy, gz | int16 각각 | 각속도, 1 LSB = 0.1deg/s |

보드 시간은 센서 내부의 하드웨어 타임스탬프가 아니라 읽기 시점입니다. 맥북 도착 시간과 구분해 CSV에 저장합니다.
100바이트 묶음은 ATT MTU 103 이상에서 전송합니다. 센서 값을 위 해상도로 양자화하며 필터나 중력 제거를 하지 않습니다.
수신기는 uint32 시간·순번 wraparound를 처리합니다. 시험 중 보드가 재시작되면 수신 프로그램도 다시 실행합니다.
자기장 3축은 이 최소 수신 시험에 포함하지 않습니다.

## 코드 확인

```sh
python3 -m unittest discover -s tests -v
```

프로토콜의 묶음 해석, 순번·시간 wraparound와 자세 계산의 축 매핑·회전·뒤집힘·정지 보정·데이터 중단 처리를 확인합니다. 기록 분석은 묶음 도착과 실제 측정 간격을 구분하고 순번 누락을 검출합니다. 실제 하드웨어 수신 시험과 별개입니다.

## 참고

- [Nano 33 BLE Rev2](https://docs.arduino.cc/hardware/nano-33-ble-rev2/)
- [Arduino CLI](https://docs.arduino.cc/arduino-cli/getting-started/)
- [Arduino_BMI270_BMM150](https://github.com/arduino-libraries/Arduino_BMI270_BMM150)
- [Bleak macOS](https://bleak.readthedocs.io/en/latest/backends/macos.html)
- [Bleak 지원 플랫폼](https://bleak.readthedocs.io/en/latest/)
- [Mahony 등의 비선형 상보 필터 연구](https://doi.org/10.1109/TAC.2008.923738)
