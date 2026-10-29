"""Permanent negative control for pytest-socket's --disable-socket.

If the flag is removed from ``addopts``, these tests fail, which is the
point: they exist to prove that the suite is offline, not to exercise
the library.

pytest-socket 0.8.x's ``SocketBlockedError.__init__`` calls
``warnings.warn(msg)``. With ``filterwarnings = ["error"]`` in
``pyproject.toml``, that warning becomes an exception raised from
inside the constructor, which makes ``pytest.raises(SocketBlockedError)``
fail even though the socket is really blocked. The ``filterwarnings``
mark below silences only that warning so the intended
``SocketBlockedError`` propagates; the block itself is still enforced by
pytest-socket.
"""

from __future__ import annotations

import socket

import pytest
from pytest_socket import SocketBlockedError

pytestmark = [
    pytest.mark.unit,
    pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning"),
]


def test_socket_socket_blocked() -> None:
    """``socket.socket`` must raise ``SocketBlockedError``."""
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_create_connection_blocked() -> None:
    """``socket.create_connection`` must raise ``SocketBlockedError``."""
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("127.0.0.1", 9), timeout=0.1)
