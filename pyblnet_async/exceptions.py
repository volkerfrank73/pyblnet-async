"""Exceptions for pyblnet-async."""

from __future__ import annotations


class BLNETError(Exception):
    """Base class for all BL-NET errors."""


class BLNETConnectionError(BLNETError):
    """The BL-NET could not be reached or did not answer like a BL-NET."""


class BLNETAuthError(BLNETError):
    """Login failed or the session was rejected (wrong password, busy device)."""


class BLNETCommandError(BLNETError):
    """A command was sent but the BL-NET did not accept it."""
