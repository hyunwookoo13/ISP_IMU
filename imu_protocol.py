"""ISP_IMU v1 samples: <IIhhhhhh>, 20 bytes each; up to 5 per notification."""
import struct
from dataclasses import dataclass

SERVICE_UUID = "9a407100-8c00-4b22-9f8d-13fbf859c8aa"
DATA_UUID = "9a407101-8c00-4b22-9f8d-13fbf859c8aa"
DEVICE_NAME = "ISP_IMU"
PACKET = struct.Struct("<IIhhhhhh")
MAX_BATCH_SAMPLES = 5
UINT32_MASK = (1 << 32) - 1


@dataclass(frozen=True)
class Sample:
    seq: int
    device_ms: int
    ax_g: float
    ay_g: float
    az_g: float
    gx_dps: float
    gy_dps: float
    gz_dps: float


def decode_packet(data: bytes) -> Sample:
    if len(data) != PACKET.size:
        raise ValueError(f"Expected {PACKET.size} bytes, got {len(data)}")
    seq, ms, ax, ay, az, gx, gy, gz = PACKET.unpack(data)
    return Sample(seq, ms, ax / 1000, ay / 1000, az / 1000,
                  gx / 10, gy / 10, gz / 10)


def decode_notification(data: bytes):
    """Decode complete samples only, supporting the original one-sample mode."""
    if not PACKET.size <= len(data) <= PACKET.size*MAX_BATCH_SAMPLES or len(data) % PACKET.size:
        raise ValueError(f"Expected 1–{MAX_BATCH_SAMPLES} complete 20-byte samples, got {len(data)} bytes")
    return tuple(decode_packet(data[offset:offset+PACKET.size])
                 for offset in range(0, len(data), PACKET.size))


class StreamStats:
    """Sequence gaps and elapsed board time, including uint32 wraparound."""

    def __init__(self) -> None:
        self.count = 0
        self.missing = 0
        self.elapsed_ms = 0
        self.previous = None

    def observe(self, sample: Sample) -> float:
        if self.previous is not None:
            step = (sample.seq - self.previous.seq) & UINT32_MASK
            dt = (sample.device_ms - self.previous.device_ms) & UINT32_MASK
            if step == 0 or step >= (1 << 31) or dt >= (1 << 31):
                raise ValueError("Non-increasing sequence/time; restart the receiver after a board reset")
            self.missing += step - 1
            self.elapsed_ms += dt
        self.previous = sample
        self.count += 1
        return self.elapsed_ms / 1000

    @property
    def rate_hz(self) -> float:
        return (self.count - 1) * 1000 / self.elapsed_ms if self.elapsed_ms else 0.0
