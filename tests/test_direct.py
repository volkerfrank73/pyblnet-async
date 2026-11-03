"""Tests for the direct (TA port) client against a fake TCP BL-NET."""

from __future__ import annotations

import asyncio
import struct

import pytest

from pyblnet_async import (
    BLNETCommandError,
    BLNETConnectionError,
    BLNETDirectClient,
    BLNETUnsupportedError,
    InputKind,
)
from pyblnet_async.direct import parse_dataset

# Recorded from the real BL-NET (UVR1611, CAN mode) on 03.11.2026.
HEADER = bytes.fromhex("0fdcbd9e00017600000040d601d4")
LATEST = bytes.fromhex(
    "8079200100000085218e21fe209220a9203b20e121f820ec202821de2000301c30"
    "a0000080808003000000004d1d56009201000024072f001c"
)


def _with_checksum(data: bytes) -> bytes:
    return data + bytes([sum(data) % 256])


class FakeTAPort:
    """Answers the commands of the BL-NET direct protocol from recorded bytes."""

    def __init__(self) -> None:
        self.mode = b"\xdc"
        self.waits = 0
        self.latest = LATEST
        self.commands: list[bytes] = []
        self.reset_ok = True
        self.port = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while command := await reader.read(1):
                if command == b"\xab":
                    command += await reader.readexactly(1)
                self.commands.append(command)
                if command == b"\x81":
                    writer.write(self.mode)
                elif command == b"\xaa":
                    writer.write(HEADER)
                elif command[:1] == b"\xab":
                    if self.waits:
                        self.waits -= 1
                        writer.write(_with_checksum(b"\xba\x00"))
                        await writer.drain()
                        break  # the device closes after asking for a pause
                    writer.write(self.latest)
                elif command == b"\xad":
                    writer.write(b"\xad")
                elif command == b"\xaf":
                    writer.write(b"\xaf" if self.reset_ok else b"")
                await writer.drain()
        finally:
            writer.close()


@pytest.fixture
async def ta():
    fake = FakeTAPort()
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    fake.port = server.sockets[0].getsockname()[1]
    yield fake
    server.close()
    await server.wait_closed()


def direct(ta, **kwargs):
    return BLNETDirectClient("127.0.0.1", port=ta.port, timeout=2, **kwargs)


def test_parse_recorded_dataset():
    data = parse_dataset(LATEST[1:56])
    assert data.inputs[1].kind is InputKind.TEMPERATURE
    assert data.inputs[1].value == 12.1
    assert data.inputs[1].unit == "°C"
    assert data.inputs[14].value == 22.2
    assert data.inputs[15].kind is InputKind.FLOW
    assert data.inputs[15].value == 0
    assert data.inputs[16].value == 112
    assert data.inputs[16].unit == "l/h"
    assert data.inputs[3].kind is InputKind.UNUSED
    assert data.inputs[3].value is None
    assert data.inputs[2].raw == 0x0001
    assert [n for n, on in data.outputs.items() if on] == [6, 8]
    assert len(data.outputs) == 16
    assert data.heat_meters[1].active is True
    assert data.heat_meters[1].power == 0.0
    assert data.heat_meters[1].energy == pytest.approx(86750.1)
    assert data.heat_meters[2].power == pytest.approx(0.16, abs=0.005)
    assert data.heat_meters[2].energy == pytest.approx(47182.8)


def test_negative_temperature():
    raw = 0xFFFF & -50  # -5.0 °C: sign bit set, two's complement in the low 12 bits
    word = (raw & 0x0FFF) | 0x2000 | 0x8000
    dataset = bytearray(LATEST[1:56])
    dataset[0:2] = struct.pack("<H", word)
    assert parse_dataset(bytes(dataset)).inputs[1].value == -5.0


def test_inactive_heat_meter():
    dataset = bytearray(LATEST[1:56])
    dataset[38] = 0x01  # only meter 1 active
    data = parse_dataset(bytes(dataset))
    assert data.heat_meters[1].active is True
    assert data.heat_meters[2].active is False


async def test_fetch(ta):
    data = await direct(ta).async_fetch()
    assert data.inputs[16].value == 112
    assert ta.commands == [b"\x81", b"\xaa", b"\xab\x01", b"\xad"]


async def test_fetch_waits_when_asked(ta):
    ta.waits = 2
    data = await direct(ta).async_fetch()
    assert data.inputs[1].value == 12.1
    assert ta.commands.count(b"\xab\x01") == 3


async def test_fetch_gives_up_after_too_many_waits(ta):
    ta.waits = 99
    with pytest.raises(BLNETConnectionError):
        await direct(ta, max_waits=2).async_fetch()


async def test_bad_checksum(ta):
    ta.latest = LATEST[:-1] + bytes([(LATEST[-1] + 1) % 256])
    with pytest.raises(BLNETConnectionError, match="checksum"):
        await direct(ta).async_fetch()


async def test_unsupported_mode(ta):
    ta.mode = b"\xa8"  # DL
    with pytest.raises(BLNETUnsupportedError):
        await direct(ta).async_fetch()


async def test_test_connection(ta):
    await direct(ta).async_test_connection()
    assert ta.commands == [b"\x81"]


async def test_not_reachable():
    with pytest.raises(BLNETConnectionError):
        await BLNETDirectClient("127.0.0.1", port=1, timeout=1).async_test_connection()


def test_digital_inputs():
    data = parse_dataset(LATEST[1:56])
    # Recorded: S2 (Heizp.Freig.) was on, S3 (PV-Anf.WP) off; both carry type bits 0 on CAN.
    assert data.inputs[2].is_on is True
    assert data.inputs[3].is_on is False
    assert data.inputs[1].is_on is None  # a temperature
    dataset = bytearray(LATEST[1:56])
    dataset[2:4] = struct.pack("<H", 0x9000)  # type "digital", bit 15 set
    assert parse_dataset(bytes(dataset)).inputs[2].is_on is True


async def test_reset_after_fetch(ta):
    data = await direct(ta, reset=True).async_fetch()
    assert data.inputs[16].value == 112
    assert ta.commands[-2:] == [b"\xad", b"\xaf"]


async def test_reset_not_confirmed(ta):
    ta.reset_ok = False
    with pytest.raises(BLNETCommandError):
        await direct(ta, reset=True).async_fetch()


async def test_no_reset_when_read_failed(ta):
    ta.latest = LATEST[:-1] + bytes([(LATEST[-1] + 1) % 256])
    with pytest.raises(BLNETConnectionError):
        await direct(ta, reset=True).async_fetch()
    assert b"\xaf" not in ta.commands


async def test_no_reset_by_default(ta):
    c = direct(ta)
    await c.async_test_connection()
    await c.async_fetch()
    assert all(cmd[:1] != b"\xaf" for cmd in ta.commands)  # RESET_DATA
