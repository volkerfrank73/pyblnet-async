import pytest

from pyblnet_async import (
    BLNETAuthError,
    BLNETClient,
    BLNETCommandError,
    BLNETConnectionError,
    DigitalCommand,
)

from .conftest import PASSWORD


def client(fake, session, **kwargs):
    kwargs.setdefault("password", PASSWORD)
    return BLNETClient("127.0.0.1", session, port=fake.port, timeout=3, **kwargs)


async def test_fetch(fake, session):
    data = await client(fake, session).async_fetch()
    assert data.analog[2].value == 46.3
    assert data.digital[2].is_on is True
    assert fake.logged_in is False  # always logs out


async def test_fetch_twice_does_not_lock_device(fake, session):
    c = client(fake, session)
    await c.async_fetch()
    await c.async_fetch()


async def test_wrong_password(fake, session):
    with pytest.raises(BLNETAuthError):
        await client(fake, session, password="wrong").async_test_connection()


async def test_test_connection_ok(fake, session):
    await client(fake, session).async_test_connection()
    assert fake.logged_in is False


async def test_not_reachable(session):
    c = BLNETClient("127.0.0.1", session, port=1, timeout=1)
    with pytest.raises(BLNETConnectionError):
        await c.async_test_connection()


async def test_set_digital_builds_request(fake, session):
    await client(fake, session).async_set_digital(10, DigitalCommand.ON)
    assert "/580600.htm?blw91A1200A=2" in fake.requests


async def test_set_digital_rejects_bad_id(fake, session):
    with pytest.raises(ValueError):
        await client(fake, session).async_set_digital(16, DigitalCommand.OFF)


async def test_node_selected_before_fetch(fake, session):
    await client(fake, session, node=3).async_fetch()
    assert "/can.htm?blaB=3" in fake.requests


async def test_concurrent_calls_are_serialized(fake, session):
    import asyncio

    c = client(fake, session)
    results = await asyncio.gather(c.async_fetch(), c.async_fetch())
    assert all(r.analog for r in results)


async def test_overrides_home_assistant_user_agent(fake):
    """HA puts its own User-Agent on the shared session; the BL-NET refuses it."""
    import aiohttp

    headers = {"User-Agent": "HomeAssistant/2026.9.4 aiohttp/3.14 Python/3.14"}
    async with aiohttp.ClientSession(headers=headers) as ha_session:
        data = await client(fake, ha_session).async_fetch()
    assert data.analog


async def test_failed_login_releases_the_device_session(fake, session):
    """Login accepted but session not valid: must log out, or the device stays busy."""
    fake.reject_cookie_on_pages = True
    with pytest.raises(BLNETAuthError):
        await client(fake, session).async_test_connection()
    assert fake.logged_in is False
    fake.reject_cookie_on_pages = False
    await client(fake, session).async_test_connection()  # works again right away
