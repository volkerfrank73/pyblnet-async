"""Data models returned by the BL-NET client."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DigitalMode(StrEnum):
    """Operating mode of a digital output."""

    AUTO = "AUTO"
    HAND = "HAND"


class DigitalCommand(StrEnum):
    """Command for a digital output, value is the code the BL-NET expects."""

    OFF = "1"
    ON = "2"
    AUTO = "3"


@dataclass(frozen=True, slots=True)
class AnalogValue:
    """An analog input (temperature etc.)."""

    id: int
    name: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class DigitalInput:
    """A digital input (read-only, e.g. a contact or a switched signal)."""

    id: int
    name: str
    is_on: bool


@dataclass(frozen=True, slots=True)
class DigitalValue:
    """A digital output (pump, valve, ...)."""

    id: int
    name: str
    mode: DigitalMode
    is_on: bool


@dataclass(frozen=True, slots=True)
class BLNETData:
    """Snapshot of one UVR node, keyed by channel id."""

    analog: dict[int, AnalogValue] = field(default_factory=dict)
    digital_inputs: dict[int, DigitalInput] = field(default_factory=dict)
    digital: dict[int, DigitalValue] = field(default_factory=dict)


class InputKind(StrEnum):
    """Sensor type of an input as encoded in the direct-port dataset."""

    UNUSED = "unused"
    DIGITAL = "digital"
    TEMPERATURE = "temperature"
    FLOW = "flow"
    RADIATION = "radiation"
    ROOM_TEMPERATURE = "room_temperature"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DirectInput:
    """An input read over the direct port; the port carries no names."""

    id: int
    kind: InputKind
    value: float | None
    unit: str | None
    raw: int

    @property
    def is_on(self) -> bool | None:
        """State of a digital input, None for measured values.

        Type "digital" carries the state in bit 15. A UVR1611 on CAN reports its
        digital inputs with type bits 0 and the state in bit 0 (S2 on = 0x0001), which
        looks the same as an unused input that is off; the caller has to know which
        inputs are digital.
        """
        if self.kind is InputKind.DIGITAL:
            return bool(self.raw & 0x8000)
        if self.kind is InputKind.UNUSED:
            return bool(self.raw & 0x0001)
        return None


@dataclass(frozen=True, slots=True)
class HeatMeter:
    """A heat meter (Wärmemengenzähler) of the UVR1611."""

    id: int
    active: bool
    power: float  # kW
    energy: float  # kWh


@dataclass(frozen=True, slots=True)
class DirectData:
    """Current dataset read over the direct port, keyed by channel id."""

    inputs: dict[int, DirectInput] = field(default_factory=dict)
    outputs: dict[int, bool] = field(default_factory=dict)
    heat_meters: dict[int, HeatMeter] = field(default_factory=dict)
