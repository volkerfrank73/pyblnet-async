# pyblnet-async

Async Python client for the Technische Alternative **BL-NET** (data logger / web interface of the UVR1611 controller).

This is an `aiohttp`-based rewrite of [nielstron/pyblnet](https://github.com/nielstron/pyblnet) (MIT), built for use in a Home Assistant integration. It reads the BL-NET web interface and, optionally, the current values over the direct port (TA port, PC-BLNET protocol).

## Installation

```bash
pip install git+https://github.com/volkerfrank73/pyblnet-async
```

Requires Python 3.12 or newer and `aiohttp`.

## Usage

```python
import asyncio
import aiohttp
from pyblnet_async import BLNETClient, DigitalCommand

async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = BLNETClient("192.168.0.250", session, password="...", node=None)
        await client.async_test_connection()   # raises on failure

        data = await client.async_fetch()
        for sensor in data.analog.values():
            print(sensor.name, sensor.value, sensor.unit)
        for output in data.digital.values():
            print(output.name, output.mode, output.is_on)

        await client.async_set_digital(1, DigitalCommand.AUTO)

asyncio.run(main())
```

- `BLNETClient(host, session, *, password=None, port=80, node=None, timeout=10)`: `node` selects the CAN node, `None` keeps the node that is active on the device.
- `async_fetch()` returns `BLNETData` with `analog` (inputs with a value and unit), `digital_inputs` (read-only on/off inputs) and `digital` (switchable outputs with mode), each a dict keyed by channel id.
- `async_set_digital(id, DigitalCommand.ON | OFF | AUTO)` for outputs 1 to 15.
- Errors derive from `BLNETError`: `BLNETConnectionError`, `BLNETAuthError`, `BLNETCommandError`, `BLNETUnsupportedError`.

### Direct port (TA port)

```python
from pyblnet_async import BLNETDirectClient

client = BLNETDirectClient("192.168.0.250", port=40000)
mode = await client.async_test_connection()   # "CAN", "DL" or "DL2"
data = await client.async_fetch()
data.inputs[16].kind, data.inputs[16].value, data.inputs[16].unit   # InputKind.FLOW, 112.0, "l/h"
data.outputs[6]                                                     # True
data.heat_meters[1].power, data.heat_meters[1].energy               # kW, kWh
```

- `BLNETDirectClient(host, *, port=40000, frame=1, timeout=10, max_waits=5, reset=False)`: `frame` is the CAN dataset (1 = first logged controller). `reset=True` clears the logger memory of the BL-NET after every successful read (like pyblnet's `reset`); the logged data is lost. Nothing is cleared after a failed read; an unconfirmed clear raises `BLNETCommandError`.
- `async_fetch()` returns `DirectData` with `inputs` (16 `DirectInput` with `kind`, `value`, `unit` and the `raw` word), `outputs` (16 booleans) and `heat_meters` (2 `HeatMeter` with `active`, `power` in kW, `energy` in kWh).
- Without `reset` read only: sends `GET_MODE`, `GET_HEADER`, `GET_LATEST` and `END_READ`. Pauses the BL-NET asks for are honoured (up to `max_waits` times), so a call can take a few seconds.
- Only the CAN logging mode is supported (`BLNETUnsupportedError` otherwise); it is the only mode tested against a real device.
- The direct port carries no names. Digital inputs: a UVR1611 on CAN reports them with type bits 0 and the state in bit 0 (on = `0x0001`, off = `0x0000`), so they decode as `UNUSED` and look like unused inputs when off. `DirectInput.is_on` gives the state; the caller has to know which inputs are digital. Values of kind `ROOM_TEMPERATURE` and `RADIATION` follow the published format but are untested.
- The direct port is independent of the web session, so it can be read while the web interface is in use.

The BL-NET refuses the `User-Agent` that Home Assistant sets on its shared session, so the client sends its own on every request.

The BL-NET allows only one logged-in session. The client serializes its calls and logs out after each one. While Home Assistant or another tool is polling, a second client may briefly get a login error and should retry later.

## Differences to pyblnet

- Async (`aiohttp`) instead of blocking `requests`; no `htmldom` dependency.
- Typed result objects (floats, booleans, enums) instead of strings like `"EIN"`.
- Distinct exceptions instead of a mix of `None`, `False` and `ValueError`.
- No retry loops inside the library; callers decide how to retry.
- Digital inputs (shown on the input page without a unit) are their own read-only category instead of being mixed into the outputs.
- Direct port: async, CAN mode only, clearing the logger memory only on request and only after a successful read; `speed` is not decoded.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Read-only check against a real device (the password comes from the environment and is never printed):

```bash
BLNET_PASSWORT=... PYTHONPATH=. .venv/bin/python tests/live_check.py 192.168.0.250
```

## License

MIT, see `LICENSE.txt`. Original work by Niels Mündler (nielstron).
