#pragma once
#include <Arduino_BMI270_BMM150.h>

// Keep the installed Arduino library intact. Its protected configuration hook
// lets this project read both sensors in one register burst, with the same
// calibration, range and axis convention as the library's public read methods.
class HighRateIMU : public BoschSensorClass {
 public:
  explicit HighRateIMU(TwoWire& bus) : BoschSensorClass(bus) {}

  // 1 = a fresh accel/gyro pair, 0 = not ready, -1 = communication failure.
  int readPair(struct bmi2_sens_data& data) {
    if (!device_) return -1;
    uint8_t status = 0;
    if (bmi2_get_status(&status, device_) != BMI2_OK) return -1;
    const uint8_t ready = BMI2_DRDY_ACC_MASK | BMI2_DRDY_GYR_MASK;
    if ((status & ready) != ready) return 0;
    // Accel (6), gyro (6), and the sensor clock (3) are contiguous at 0x0c.
    // Avoid the generic API's redundant power-control and sensor-time reads.
    uint8_t bytes[15];
    if (bmi2_get_regs(BMI2_ACC_X_LSB_ADDR, bytes, sizeof(bytes), device_) != BMI2_OK)
      return -1;
    int16_t acceleration[3], gyro[3];
    for (int index = 0; index < 3; ++index) {
      acceleration[index] = signedWord(bytes + index * 2);
      gyro[index] = signedWord(bytes + 6 + index * 2);
    }
    // Match Bosch's bundled driver's integer cross-axis correction and clipping.
    int32_t correction = static_cast<int16_t>(
        (static_cast<int32_t>(device_->gyr_cross_sens_zx) * gyro[2]) / 512);
    int32_t corrected = static_cast<int32_t>(gyro[0]) - correction;
    if (corrected > 32767) corrected = 32767;
    if (corrected < -32768) corrected = -32768;
    gyro[0] = static_cast<int16_t>(corrected);
    remap(acceleration, data.acc);
    remap(gyro, data.gyr);
    data.sens_time = bytes[12] | (static_cast<uint32_t>(bytes[13]) << 8)
                           | (static_cast<uint32_t>(bytes[14]) << 16);
    return 1;
  }

 protected:
  int8_t configure_sensor(struct bmi2_dev* device) override {
    device_ = device;
    int8_t result = BoschSensorClass::configure_sensor(device);
    if (result != BMI2_OK) return result;
    // Continuous 100 Hz acquisition: remove per-access power-save wake delays.
    return bmi2_set_adv_power_save(BMI2_DISABLE, device);
  }

 private:
  static int16_t signedWord(const uint8_t* bytes) {
    return static_cast<int16_t>(bytes[0] | (static_cast<uint16_t>(bytes[1]) << 8));
  }

  void remap(const int16_t* values, struct bmi2_sens_axes_data& out) {
    const auto& axes = device_->remap;
    out.x = values[axes.x_axis] * (axes.x_axis_sign == BMI2_POS_SIGN ? 1 : -1);
    out.y = values[axes.y_axis] * (axes.y_axis_sign == BMI2_POS_SIGN ? 1 : -1);
    out.z = values[axes.z_axis] * (axes.z_axis_sign == BMI2_POS_SIGN ? 1 : -1);
  }

  struct bmi2_dev* device_ = nullptr;
};
