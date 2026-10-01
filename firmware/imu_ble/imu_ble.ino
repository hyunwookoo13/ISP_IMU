#include <Arduino.h>
#include <ArduinoBLE.h>
#include "high_rate_imu.h"
#include <ctype.h>
#include <math.h>
#include <stdio.h>

// Nano 33 BLE Rev2 (BMI270). No USB/Serial connection is required to boot.
const char SERVICE_UUID[] = "9a407100-8c00-4b22-9f8d-13fbf859c8aa";
const char DATA_UUID[] = "9a407101-8c00-4b22-9f8d-13fbf859c8aa";
// BMI270 accel and gyro are both configured to 100 Hz by the Arduino library.
// Fresh-data flags pace acquisition; no delay is added after reading a sample.
const uint32_t STATUS_POLL_US = 500;
// USB text output can block acquisition. Enable only for diagnostic builds.
const bool LOG_USB_DIAGNOSTICS = false;
const int PACKET_BYTES = 20;
const int BATCH_SAMPLES = 5;
const int NOTIFICATION_BYTES = PACKET_BYTES * BATCH_SAMPLES;

BLEService imuService(SERVICE_UUID);
BLECharacteristic imuData(DATA_UUID, BLERead | BLENotify, NOTIFICATION_BYTES, false);
HighRateIMU sensor(Wire1);
// A per-board name prevents a classroom full of identical sketches from
// appearing as one indistinguishable ISP_IMU peripheral.
char advertisedName[15];  // "ISP_IMU_" + six hexadecimal address digits + NUL.

uint32_t sequence = 0;
uint32_t lastSampleMs = 0;
uint32_t lastLogMs = 0;
uint32_t lastPollUs = 0;
uint32_t previousSensorTicks = 0;
uint32_t readErrors = 0, notifyErrors = 0, longSensorIntervals = 0;
uint32_t maxReadUs = 0, maxNotifyUs = 0;
uint32_t lastLogSequence = 0;
bool haveSensorTime = false;
uint8_t notification[NOTIFICATION_BYTES];
uint8_t batchCount = 0;
float ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;
bool haveSample = false;

void putU32LE(uint8_t *out, uint32_t value) {
  for (int i = 0; i < 4; ++i) out[i] = (value >> (8 * i)) & 0xff;
}

void putI16LE(uint8_t *out, int16_t value) {
  uint16_t bits = static_cast<uint16_t>(value);
  out[0] = bits & 0xff;
  out[1] = (bits >> 8) & 0xff;
}

int16_t scaledValue(float value, float scale) {
  long result = lroundf(value * scale);
  if (result < -32768) result = -32768;
  if (result > 32767) result = 32767;
  return static_cast<int16_t>(result);
}

void haltWithError(const char *message) {
  // Initialization failure: fast blinking. USB logs are optional.
  while (true) {
    if (Serial) Serial.println(message);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(LED_BUILTIN, LOW);
    delay(400);
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  // Deliberately omit `while (!Serial)`: the power bank has no USB host.
  // This mode initializes BOTH accel and gyro, and skips the unused magnetometer.
  if (!sensor.begin(BOSCH_ACCELEROMETER_ONLY)) haltWithError("ERROR: IMU initialization failed");
  Wire1.setClock(400000);
  if (!BLE.begin()) haltWithError("ERROR: BLE initialization failed");

  String address = BLE.address();
  char suffix[7] = {};
  int suffixIndex = 5;
  for (int index = address.length() - 1; index >= 0 && suffixIndex >= 0; --index) {
    if (isxdigit(static_cast<unsigned char>(address[index])))
      suffix[suffixIndex--] = toupper(static_cast<unsigned char>(address[index]));
  }
  if (suffixIndex >= 0) haltWithError("ERROR: BLE address unavailable");
  snprintf(advertisedName, sizeof(advertisedName), "ISP_IMU_%s", suffix);
  if (!BLE.setLocalName(advertisedName)) haltWithError("ERROR: BLE name too long");
  BLE.setDeviceName(advertisedName);
  // A preference (15–30 ms); the Mac decides the actual connection interval.
  BLE.setConnectionInterval(12, 24);
  BLE.setAdvertisedService(imuService);
  imuService.addCharacteristic(imuData);
  BLE.addService(imuService);
  uint8_t initial[PACKET_BYTES] = {};
  imuData.writeValue(initial, PACKET_BYTES);
  BLE.advertise();
}

void loop() {
  BLE.poll();
  digitalWrite(LED_BUILTIN, BLE.connected() ? HIGH : LOW);
  if (!imuData.subscribed()) batchCount = 0;

  uint32_t nowUs = micros();
  if (static_cast<uint32_t>(nowUs - lastPollUs) >= STATUS_POLL_US) {
    lastPollUs = nowUs;
    struct bmi2_sens_data data = {};
    uint32_t readStartUs = micros();
    int result = sensor.readPair(data);
    uint32_t readUs = micros() - readStartUs;
    if (result < 0) ++readErrors;
    if (result == 1) {
      if (readUs > maxReadUs) maxReadUs = readUs;
      // Preserve the installed library's Nano XYZ convention and units.
      ax = -data.acc.y / 8192.0f;
      ay = -data.acc.x / 8192.0f;
      az = data.acc.z / 8192.0f;
      gx = -data.gyr.y / 16.384f;
      gy = -data.gyr.x / 16.384f;
      gz = data.gyr.z / 16.384f;
      // Sensor time is a free-running 24-bit clock (256 ticks per 10 ms).
      // Count read gaps over 15 ms separately from BLE sequence gaps.
      if (haveSensorTime && ((data.sens_time - previousSensorTicks) & 0xffffff) > 384)
        ++longSensorIntervals;
      previousSensorTicks = data.sens_time;
      haveSensorTime = true;
      lastSampleMs = millis();
      uint8_t packet[PACKET_BYTES];
      putU32LE(packet, sequence++);
      putU32LE(packet + 4, lastSampleMs);
      putI16LE(packet + 8, scaledValue(ax, 1000.0f));
      putI16LE(packet + 10, scaledValue(ay, 1000.0f));
      putI16LE(packet + 12, scaledValue(az, 1000.0f));
      putI16LE(packet + 14, scaledValue(gx, 10.0f));
      putI16LE(packet + 16, scaledValue(gy, 10.0f));
      putI16LE(packet + 18, scaledValue(gz, 10.0f));
      // Five complete v1 samples per notification. Mac/Nano negotiated MTU 247;
      // a 100-byte notification requires ATT MTU >=103. Each sample retains
      // its own sequence and actual read timestamp; no timestamps are invented.
      if (imuData.subscribed()) {
        memcpy(notification + batchCount * PACKET_BYTES, packet, PACKET_BYTES);
        if (++batchCount == BATCH_SAMPLES) {
          uint32_t notifyStartUs = micros();
          if (!imuData.writeValue(notification, NOTIFICATION_BYTES)) ++notifyErrors;
          uint32_t notifyUs = micros() - notifyStartUs;
          if (notifyUs > maxNotifyUs) maxNotifyUs = notifyUs;
          batchCount = 0;
        }
      }
      haveSample = true;
    }
  }

  uint32_t now = millis();
  if (LOG_USB_DIAGNOSTICS && Serial && haveSample && static_cast<uint32_t>(now - lastLogMs) >= 1000) {
    float rate = (sequence - lastLogSequence) * 1000.0f / (now - lastLogMs);
    lastLogMs = now;
    lastLogSequence = sequence;
    Serial.print("IMU seq="); Serial.print(sequence - 1);
    Serial.print(" accel_g="); Serial.print(ax, 3);
    Serial.print(','); Serial.print(ay, 3);
    Serial.print(','); Serial.print(az, 3);
    Serial.print(" gyro_dps="); Serial.print(gx, 1);
    Serial.print(','); Serial.print(gy, 1);
    Serial.print(','); Serial.print(gz, 1);
    Serial.print(" BLE="); Serial.print(BLE.connected() ? "connected" : "advertising");
    Serial.print(" rate_hz="); Serial.print(rate, 1);
    Serial.print(" read_max_us="); Serial.print(maxReadUs);
    Serial.print(" notify_max_us="); Serial.print(maxNotifyUs);
    Serial.print(" read_errors="); Serial.print(readErrors);
    Serial.print(" notify_errors="); Serial.print(notifyErrors);
    Serial.print(" sensor_read_gaps_gt15ms="); Serial.println(longSensorIntervals);
  }
}
