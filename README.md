# pyblnet-async

Async Python client for the Technische Alternative **BL-NET** (data logger / web interface of the UVR1611 controller).

This is an `aiohttp`-based rewrite of [nielstron/pyblnet](https://github.com/nielstron/pyblnet) (MIT), built for use in a Home Assistant integration. It talks to the BL-NET web interface only; the PC-BLNET direct (TA) port is not supported.

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
- `async_fetch()` returns `BLNETData` with `analog` and `digital`, each a dict keyed by channel id.
- `async_set_digital(id, DigitalCommand.ON | OFF | AUTO)` for outputs 1 to 15.
- Errors derive from `BLNETError`: `BLNETConnectionError`, `BLNETAuthError`, `BLNETCommandError`.

The BL-NET allows only one logged-in session. The client serializes its calls and logs out after each one. While Home Assistant or another tool is polling, a second client may briefly get a login error and should retry later.

## Differences to pyblnet

- Async (`aiohttp`) instead of blocking `requests`; no `htmldom` dependency.
- Typed result objects (floats, booleans, enums) instead of strings like `"EIN"`.
- Distinct exceptions instead of a mix of `None`, `False` and `ValueError`.
- No retry loops inside the library; callers decide how to retry.
- Dropped: direct TA port, `speed`/`power`/`energy` (the web interface never provided them).

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
