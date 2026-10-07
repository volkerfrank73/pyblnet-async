"""Parse the HTML pages of the BL-NET web interface.

The pages are plain HTML where each channel is rendered as
``&nbsp;<id>:&nbsp;<name><br>&nbsp;...<value>``. We turn ``<br>`` into newlines,
drop the remaining tags and match with regular expressions.
"""

from __future__ import annotations

import html
import re

from .models import AnalogValue, DigitalInput, DigitalMode, DigitalValue

_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HEAD = re.compile(r'<div id="head">(.*?)</div>', re.IGNORECASE | re.DOTALL)
_BODY = re.compile(r"<body.*", re.IGNORECASE | re.DOTALL)

_ANALOG = re.compile(
    r"(?P<id>\d+):&nbsp;(?P<name>.+)\n(&nbsp;){3,6}"
    r"(?P<value>(-&nbsp;)?\d+,\d+) (?P<unit>.+?) &nbsp;&nbsp;PAR\?"
)
_DIGITAL_INPUT = re.compile(
    r"(?P<id>\d+):&nbsp;(?P<name>.+)\n(&nbsp;)+"
    r"(?P<value>AUS|EIN|OFF|ON)(&nbsp;)+PAR\?"
)
_DIGITAL = re.compile(
    r"(?P<id>\d+):&nbsp;(?P<name>.+)\n&nbsp;&nbsp;&nbsp;&nbsp;"
    r"(?P<mode>AUTO|HAND)/(?P<value>AUS|EIN)"
)


def _text(page: str) -> str:
    """Return the body of a page with line breaks kept and tags removed."""
    body = _BODY.search(page)
    return _TAG.sub("", _BR.sub("\n", body.group(0) if body else page))


def _clean(value: str) -> str:
    return html.unescape(value.replace("&nbsp;", " ")).strip()


def is_blnet_page(page: str) -> bool:
    """Whether a page looks like a BL-NET answer (also the access-denied page)."""
    title = _TITLE.search(page)
    if title and "bl-net" in title.group(1).lower():
        return True
    head = _HEAD.search(page)
    return bool(head and "BL-NET" in head.group(1))


def is_access_denied(page: str) -> bool:
    """Whether the page is the BL-NET 'access denied' page."""
    title = _TITLE.search(page)
    return bool(title and "zugang verweigert" in title.group(1).lower())


def parse_analog(page: str) -> dict[int, AnalogValue]:
    """Parse ``580500.htm`` into analog values."""
    result: dict[int, AnalogValue] = {}
    for match in _ANALOG.finditer(_text(page)):
        channel = int(match["id"])
        value = match["value"].replace("&nbsp;", "").replace(",", ".")
        result[channel] = AnalogValue(
            id=channel,
            name=_clean(match["name"]),
            value=float(value),
            unit=_clean(match["unit"]),
        )
    return result


def parse_digital_inputs(page: str) -> dict[int, DigitalInput]:
    """Parse the digital inputs, which are listed on ``580500.htm`` between the analog ones."""
    result: dict[int, DigitalInput] = {}
    for match in _DIGITAL_INPUT.finditer(_text(page)):
        channel = int(match["id"])
        result[channel] = DigitalInput(
            id=channel,
            name=_clean(match["name"]),
            is_on=match["value"] in ("EIN", "ON"),
        )
    return result


def parse_digital(page: str) -> dict[int, DigitalValue]:
    """Parse ``580600.htm`` into digital outputs."""
    result: dict[int, DigitalValue] = {}
    for match in _DIGITAL.finditer(_text(page)):
        channel = int(match["id"])
        result[channel] = DigitalValue(
            id=channel,
            name=_clean(match["name"]),
            mode=DigitalMode(match["mode"]),
            is_on=match["value"] == "EIN",
        )
    return result
