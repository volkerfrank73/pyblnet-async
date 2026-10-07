from pathlib import Path

from pyblnet_async import DigitalMode
from pyblnet_async.parser import (
    is_access_denied,
    is_blnet_page,
    parse_analog,
    parse_digital,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return FIXTURES.joinpath(name).read_text("iso-8859-1")


def test_parse_analog():
    values = parse_analog(read("580500.htm"))
    assert sorted(values) == [1, 2, 3, 4, 5, 6, 7, 9]
    assert values[2].name == "TSP.oben"
    assert values[2].value == 46.3
    assert values[2].unit == "°C"
    assert values[5].value == -72.3


def test_parse_digital():
    values = parse_digital(read("580600.htm"))
    assert sorted(values) == [1, 2, 5, 6, 7, 10]
    assert values[2].is_on is True
    assert values[2].mode is DigitalMode.AUTO
    assert values[6].is_on is False
    assert values[6].mode is DigitalMode.HAND
    assert values[10].name == "WW-Pumpe1"


def test_parse_garbage_gives_empty():
    assert parse_analog("<html><body>nothing</body></html>") == {}
    assert parse_digital("") == {}


def test_page_detection():
    assert is_blnet_page(read("main.html"))
    assert not is_blnet_page("<html><title>Router</title></html>")
    assert not is_access_denied(read("580500.htm"))
