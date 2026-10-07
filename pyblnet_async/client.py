"""Async client for the BL-NET web interface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiohttp

from .exceptions import (
    BLNETAuthError,
    BLNETCommandError,
    BLNETConnectionError,
)
from .models import BLNETData, DigitalCommand
from .parser import is_access_denied, is_blnet_page, parse_analog, parse_digital

_PROBE_PATH = "/par.htm?blp=A1200101&1238653"
_MAX_DIGITAL_ID = 15


class BLNETClient:
    """Talk to a BL-NET over HTTP.

    The device allows only one logged-in session, so all calls are serialized
    with a lock and every call logs out again when it is done.
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        password: str | None = None,
        port: int = 80,
        node: int | None = None,
        timeout: float = 10,
    ) -> None:
        host = host.removeprefix("http://").removeprefix("https://").rstrip("/")
        self._base = f"http://{host}:{port}"
        self._session = session
        self._password = password
        self._node = node
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._taid = ""

    async def async_test_connection(self) -> None:
        """Check that a BL-NET answers and the credentials work.

        Raises BLNETConnectionError or BLNETAuthError.
        """
        async with self._lock:
            page = await self._get("/")
            if not is_blnet_page(page):
                raise BLNETConnectionError(f"No BL-NET found at {self._base}")
            async with self._logged_in():
                pass

    async def async_fetch(self) -> BLNETData:
        """Read all analog and digital values of the selected node."""
        async with self._lock, self._logged_in():
            await self._select_node()
            analog_page = await self._get("/580500.htm")
            digital_page = await self._get("/580600.htm")
        for page in (analog_page, digital_page):
            if is_access_denied(page):
                raise BLNETAuthError("BL-NET denied access")
        return BLNETData(
            analog=parse_analog(analog_page),
            digital=parse_digital(digital_page),
        )

    async def async_set_digital(
        self, digital_id: int, command: DigitalCommand
    ) -> None:
        """Switch a digital output on, off or back to automatic."""
        if not 1 <= digital_id <= _MAX_DIGITAL_ID:
            raise ValueError(f"digital_id must be 1..{_MAX_DIGITAL_ID}, got {digital_id}")
        async with self._lock, self._logged_in():
            await self._select_node()
            path = f"/580600.htm?blw91A1200{digital_id:X}={command.value}"
            if not await self._request_keeps_session(path):
                raise BLNETCommandError(
                    f"BL-NET did not accept {command.name} for output {digital_id}"
                )

    @asynccontextmanager
    async def _logged_in(self) -> AsyncIterator[None]:
        """Log in, yield, always log out again."""
        await self._log_in()
        try:
            yield
        finally:
            await self._log_out()

    async def _log_in(self) -> None:
        if self._password is None:
            return
        payload = {"blu": 1, "blp": self._password, "bll": "Login"}
        try:
            async with self._session.post(
                f"{self._base}/main.html", data=payload, timeout=self._timeout
            ) as resp:
                self._taid = resp.headers.get("Set-Cookie", "")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BLNETConnectionError(f"Login request failed: {err}") from err
        if not await self._session_valid():
            raise BLNETAuthError("Login failed (wrong password or device busy)")

    async def _log_out(self) -> None:
        if self._password is None:
            return
        try:
            await self._get("/main.html?blL=1")
        except BLNETConnectionError:
            pass  # nothing more we can do, the device times the session out itself
        self._taid = ""

    async def _select_node(self) -> None:
        if self._node is None:
            return
        if not await self._request_keeps_session(f"/can.htm?blaB={self._node}"):
            raise BLNETCommandError(f"Could not select CAN node {self._node}")

    async def _session_valid(self) -> bool:
        return await self._request_keeps_session(_PROBE_PATH)

    async def _request_keeps_session(self, path: str) -> bool:
        """GET a page and report whether the device still treats us as logged in."""
        try:
            async with self._session.get(
                self._base + path,
                headers={"Cookie": self._taid},
                timeout=self._timeout,
            ) as resp:
                await resp.read()
                return self._password is None or "Set-Cookie" in resp.headers
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BLNETConnectionError(f"Request to {path} failed: {err}") from err

    async def _get(self, path: str) -> str:
        try:
            async with self._session.get(
                self._base + path,
                headers={"Cookie": self._taid},
                timeout=self._timeout,
            ) as resp:
                return (await resp.read()).decode("iso-8859-1")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BLNETConnectionError(f"Request to {path} failed: {err}") from err
