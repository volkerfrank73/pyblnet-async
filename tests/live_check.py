"""Read-only check against a real BL-NET. Usage: BLNET_PASSWORT=... python tests/live_check.py HOST"""

import asyncio
import os
import sys

import aiohttp

from pyblnet_async import BLNETClient


async def main(host: str) -> None:
    async with aiohttp.ClientSession() as session:
        client = BLNETClient(host, session, password=os.environ.get("BLNET_PASSWORT"))
        await client.async_test_connection()
        print("Verbindung und Login ok")
        data = await client.async_fetch()
        for v in data.analog.values():
            print(f"analog  {v.id:>2} {v.name:<20} {v.value} {v.unit}")
        for v in data.digital.values():
            print(f"digital {v.id:>2} {v.name:<20} {v.mode.value}/{'EIN' if v.is_on else 'AUS'}")


asyncio.run(main(sys.argv[1]))
