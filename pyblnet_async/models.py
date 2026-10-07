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
