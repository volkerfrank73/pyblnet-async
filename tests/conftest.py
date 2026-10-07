"""Fake BL-NET served from the recorded HTML pages."""

from __future__ import annotations

from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "0123"
COOKIE = 'TAID="AAAA"'


class FakeBLNET:
    """Single-session BL-NET: one login at a time, pages need the cookie."""

    def __init__(self) -> None:
        self.logged_in = False
        self.requests: list[str] = []
        self.blocked = False

    def _page(self, name: str, headers: dict[str, str] | None = None) -> web.Response:
        body = FIXTURES.joinpath(name).read_bytes()
        return web.Response(body=body, content_type="text/html", headers=headers)

    def _authed(self, request: web.Request) -> bool:
        return self.logged_in and request.headers.get("Cookie") == COOKIE

    async def root(self, request: web.Request) -> web.Response:
        self.requests.append(request.path_qs)
        return self._page("main.html")

    async def login(self, request: web.Request) -> web.Response:
        self.requests.append("POST " + request.path)
        data = await request.post()
        if data.get("blp") != PASSWORD or self.logged_in or self.blocked:
            return web.Response(status=403)
        self.logged_in = True
        return web.Response(text="ok", headers={"Set-Cookie": COOKIE})

    async def page(self, request: web.Request) -> web.Response:
        self.requests.append(request.path_qs)
        if request.query_string == "blL=1":
            self.logged_in = False
            return web.Response(text="bye")
        if not self._authed(request):
            return web.Response(status=403)
        name = request.path.lstrip("/")
        if name in ("580500.htm", "580600.htm"):
            return self._page(name, {"Set-Cookie": COOKIE})
        return web.Response(text="ok", headers={"Set-Cookie": COOKIE})


@pytest.fixture
async def fake():
    blnet = FakeBLNET()
    app = web.Application()
    app.router.add_get("/", blnet.root)
    app.router.add_post("/main.html", blnet.login)
    app.router.add_get("/main.html", blnet.page)
    app.router.add_get("/{name}", blnet.page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    blnet.port = site._server.sockets[0].getsockname()[1]
    yield blnet
    await runner.cleanup()


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess
