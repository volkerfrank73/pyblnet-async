"""Async client for the BL-NET direct port (PC-BLNET protocol, "TA port", default 40000).

Reads the current dataset ("get latest"). Only with ``reset=True`` does the client
clear the logger memory of the BL-NET after a successful read (like pyblnet's
``reset`` option); by default the logged data stays untouched.

Protocol after nielstron/pyblnet (MIT) and berwinter/uvr1611. Only the CAN mode is
supported, as it is the only one verified against a real device.
"""

from __future__ import annotations

import asyncio
import struct

from .exceptions import BLNETCommandError, BLNETConnectionError, BLNETUnsupportedError
from .models import DirectData, DirectInput, HeatMeter, InputKind

_GET_MODE = b"\x81"
_GET_HEADER = b"\xaa"
_GET_LATEST = 0xAB
_END_READ = b"\xad"
_RESET_DATA = b"\xaf"
_WAIT_TIME = 0xBA
_MODES = {b"\xdc": "CAN", b"\xa8": "DL", b"\xd1": "DL2"}
_HEADER_SIZE = 21  # upper bound, the BL-NET answers with fewer bytes
_LATEST_SIZE = 57  # frame id, 55 byte dataset, checksum
_DATASET = struct.Struct("<16HH4sBLHHLHH")
_IDLE = 1.0  # an answer shorter than requested ends after this pause

_KINDS = {
    0x0000: InputKind.UNUSED,
    0x1000: InputKind.DIGITAL,
    0x2000: InputKind.TEMPERATURE,
    0x3000: InputKind.FLOW,
    0x6000: InputKind.RADIATION,
    0x7000: InputKind.ROOM_TEMPERATURE,
}


def _signed(value: int, mask: int, sign: int) -> int:
    result = value & mask
    if value & sign:
        result = -((result ^ mask) + 1)
    return result


def _checksum_ok(data: bytes) -> bool:
    return len(data) > 1 and sum(data[:-1]) % 256 == data[-1]


def _input(channel: int, raw: int) -> DirectInput:
    kind = _KINDS.get(raw & 0x7000, InputKind.UNKNOWN)
    value: float | None = None
    unit: str | None = None
    if kind is InputKind.DIGITAL:
        value = 1.0 if raw & 0x8000 else 0.0
    elif kind is InputKind.TEMPERATURE:
        value, unit = round(_signed(raw, 0x0FFF, 0x8000) * 0.1, 1), "°C"
    elif kind is InputKind.ROOM_TEMPERATURE:
        value, unit = round(_signed(raw, 0x01FF, 0x8000) * 0.1, 1), "°C"
    elif kind is InputKind.FLOW:
        value, unit = float((raw & 0x0FFF) * 4), "l/h"
    elif kind is InputKind.RADIATION:
        value, unit = float(_signed(raw, 0x0FFF, 0x8000)), "W/m²"
    return DirectInput(id=channel, kind=kind, value=value, unit=unit, raw=raw)


def parse_dataset(dataset: bytes) -> DirectData:
    """Decode one 55 byte UVR1611 dataset (without frame id and checksum)."""
    values = _DATASET.unpack(dataset[: _DATASET.size])
    inputs = {n + 1: _input(n + 1, values[n]) for n in range(16)}
    digital = values[16]
    outputs = {n + 1: bool(digital & (1 << n)) for n in range(16)}
    active = values[18]
    meters: dict[int, HeatMeter] = {}
    for idx, (power, kwh, mwh) in enumerate((values[19:22], values[22:25])):
        meters[idx + 1] = HeatMeter(
            id=idx + 1,
            active=bool(active & (1 << idx)),
            power=round(_signed(power, 0xFFFFFFFF, 0x80000000) / 2560, 2),
            energy=round(mwh * 1000 + _signed(kwh, 0xFFFF, 0x8000) * 0.1, 1),
        )
    return DirectData(inputs=inputs, outputs=outputs, heat_meters=meters)


class _Connection:
    """One TCP connection to the direct port."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, timeout: float) -> None:
        self._reader = reader
        self._writer = writer
        self._timeout = timeout

    async def query(self, command: bytes, length: int) -> bytes:
        """Send a command, read up to length bytes; a shorter answer ends after a pause."""
        self._writer.write(command)
        await self._writer.drain()
        data = b""
        wait = self._timeout
        while len(data) < length:
            try:
                chunk = await asyncio.wait_for(self._reader.read(length - len(data)), wait)
            except TimeoutError:
                break
            if not chunk:
                break
            data += chunk
            wait = _IDLE
        return data

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except OSError:
            pass


class BLNETDirectClient:
    """Read the current values over the BL-NET direct port.

    Calls are serialized; each call opens its own connections and closes them again.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 40000,
        frame: int = 1,
        timeout: float = 10,
        max_waits: int = 5,
        reset: bool = False,
    ) -> None:
        self._host = host.removeprefix("http://").removeprefix("https://").rstrip("/")
        self._port = port
        self._frame = frame
        self._timeout = timeout
        self._max_waits = max_waits
        self._reset = reset
        self._lock = asyncio.Lock()

    async def async_test_connection(self) -> str:
        """Check that the direct port answers; return the logging mode (CAN, DL, DL2)."""
        async with self._lock:
            return await self._mode()

    async def async_fetch(self) -> DirectData:
        """Read the current dataset of the configured CAN frame."""
        async with self._lock:
            mode = await self._mode()
            if mode != "CAN":
                raise BLNETUnsupportedError(f"Logging mode {mode} is not supported, only CAN")
            conn = await self._connect()
            try:
                header = await conn.query(_GET_HEADER, _HEADER_SIZE)
                if len(header) < 6 or not _checksum_ok(header):
                    raise BLNETConnectionError("Invalid header from the direct port")
                if not 1 <= self._frame <= header[5]:
                    raise BLNETConnectionError(
                        f"Frame {self._frame} not available, the BL-NET logs {header[5]}"
                    )
                command = bytes([_GET_LATEST, self._frame])
                for _ in range(self._max_waits + 1):
                    data = await conn.query(command, _LATEST_SIZE)
                    if not (len(data) >= 3 and data[0] == _WAIT_TIME and _checksum_ok(data[:3])):
                        break
                    # The BL-NET asks for a pause (seconds in data[1]) and expects a new connection.
                    await conn.close()
                    await asyncio.sleep(data[1])
                    conn = await self._connect()
                else:
                    raise BLNETConnectionError("BL-NET kept asking to wait")
                if len(data) < _LATEST_SIZE:
                    raise BLNETConnectionError(
                        f"Short answer from the direct port ({len(data)} byte)"
                    )
                if not _checksum_ok(data):
                    raise BLNETConnectionError("Dataset checksum mismatch")
                result = parse_dataset(data[1:56])
            except BaseException:
                await self._end(conn, reset=False)  # never clear the memory after a failed read
                raise
            await self._end(conn, reset=self._reset)
        return result

    async def _mode(self) -> str:
        conn = await self._connect()
        try:
            mode = await conn.query(_GET_MODE, 1)
        finally:
            await conn.close()
        if mode not in _MODES:
            raise BLNETConnectionError(f"Unexpected answer to GET_MODE: {mode.hex() or 'none'}")
        return _MODES[mode]

    async def _end(self, conn: _Connection, *, reset: bool) -> None:
        """END_READ; with reset also clear the logger memory (RESET_DATA)."""
        try:
            ended = await conn.query(_END_READ, 1)
            if not reset:
                return
            if ended != _END_READ:
                raise BLNETCommandError("END_READ not confirmed, logger memory not cleared")
            if await conn.query(_RESET_DATA, 1) != _RESET_DATA:
                raise BLNETCommandError("BL-NET did not confirm clearing the logger memory")
        except OSError as err:
            if reset:
                raise BLNETConnectionError(f"Clearing the logger memory failed: {err}") from err
        finally:
            await conn.close()

    async def _connect(self) -> _Connection:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, TimeoutError) as err:
            raise BLNETConnectionError(
                f"Direct port {self._host}:{self._port} not reachable: {err}"
            ) from err
        return _Connection(reader, writer, self._timeout)
