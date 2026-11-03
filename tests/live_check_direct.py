"""Read-only check of the BL-NET direct port (PC-BLNET, default 40000). Usage: python tests/live_check_direct.py HOST [PORT]

Reads the current dataset with "get latest" and prints analog values, digital outputs and the two heat meters.
Sends only GET_MODE, GET_HEADER, GET_LATEST and END_READ, never RESET_DATA, so the logger memory stays untouched.
Protocol after nielstron/pyblnet (MIT) and berwinter/uvr1611; standard library only.
"""

import socket
import struct
import sys
import time

GET_MODE = b"\x81"
GET_HEADER = b"\xaa"
GET_LATEST = 0xAB
END_READ = b"\xad"
WAIT_TIME = 0xBA
MODES = {b"\xdc": "CAN", b"\xa8": "DL", b"\xd1": "DL2"}
LATEST_SIZE = 57  # 1 byte frame id, 55 byte dataset, padding, checksum
TIMEOUT = 10


def query(sock: socket.socket, command: bytes, length: int) -> bytes:
    """Send one command and read up to length bytes; shorter answers end after a 1 s pause."""
    sock.settimeout(TIMEOUT)
    sock.sendall(command)
    data = b""
    try:
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
            sock.settimeout(1)
    except TimeoutError:
        pass
    return data


def connect(host: str, port: int) -> socket.socket:
    return socket.create_connection((host, port), timeout=TIMEOUT)


def checksum_ok(data: bytes) -> bool:
    return len(data) > 1 and sum(data[:-1]) % 256 == data[-1]


def signed(value: int, mask: int, sign: int) -> int:
    result = value & mask
    if value & sign:
        result = -((result ^ mask) + 1)
    return result


def analog(raw: int) -> str:
    kind = raw & 0x7000
    if kind == 0x2000:
        return f"{signed(raw, 0x0FFF, 0x8000) * 0.1:.1f} °C"
    if kind == 0x3000:
        return f"{signed(raw, 0x0FFF, 0x8000) * 4} l/h"
    if kind == 0x1000:
        return "EIN" if raw & 0x8000 else "AUS"
    if kind == 0x0000:
        return "nicht belegt"
    return f"Rohwert {raw:#06x}"


def parse(dataset: bytes) -> None:
    values = struct.unpack("<16HH4sBLHHLHH", dataset[:55])
    for channel in range(16):
        print(f"analog  {channel + 1:>2} {analog(values[channel])}")
    digital = values[16]
    print("digital " + " ".join(f"A{n + 1}={'1' if digital & (1 << n) else '0'}" for n in range(16)))
    active = values[18]
    print(f"WMZ aktiv-Byte: {active:#04x}")
    for idx, (power, kwh, mwh) in enumerate([values[19:22], values[22:25]]):
        state = "aktiv" if active & (1 << idx) else "nicht aktiv"
        power_kw = signed(power, 0xFFFFFFFF, 0x80000000) / 2560
        energy_kwh = mwh * 1000 + signed(kwh, 0xFFFF, 0x8000) * 0.1
        print(f"WMZ {idx + 1}: {state}, Leistung {power_kw:.2f} kW, Wärmemenge {energy_kwh:.1f} kWh")


def main(host: str, port: int) -> None:
    with connect(host, port) as sock:
        mode = query(sock, GET_MODE, 1)
    print(f"Modus: {MODES.get(mode, mode.hex())}")
    if mode not in MODES:
        sys.exit("Modus nicht unterstützt")
    sock = connect(host, port)
    try:
        frames = 1
        if MODES[mode] == "CAN":
            header = query(sock, GET_HEADER, 21)
            print(f"Header: {header.hex()} (Prüfsumme {'ok' if checksum_ok(header) else 'FALSCH'})")
            frames = header[5]
            print(f"CAN-Datensätze: {frames}")
        for frame in range(1, frames + 1):
            for _ in range(5):
                data = query(sock, struct.pack("<2B", GET_LATEST, frame), LATEST_SIZE)
                if len(data) >= 2 and data[0] == WAIT_TIME and checksum_ok(data):
                    print(f"Datensatz {frame}: BL-NET bittet um {data[1]} s Wartezeit")
                    sock.close()
                    time.sleep(data[1])
                    sock = connect(host, port)
                    continue
                break
            print(f"Datensatz {frame}: {len(data)} Byte, Prüfsumme {'ok' if checksum_ok(data) else 'FALSCH'}")
            print(f"roh: {data.hex()}")
            if len(data) >= 56:
                parse(data[1:56])
    finally:
        query(sock, END_READ, 1)
        sock.close()


main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40000)
