#!/usr/bin/env python3
"""Tests for the active_reconnect toggle. Run: python3 tests/test_active_reconnect.py"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_classic_reconnect as _bumble_stub  # noqa: E402,F401  stubs bumble before classic loads
import classic  # noqa: E402
from config import Config, config  # noqa: E402


def _ini(text):
    """A Config that writes to a temp config.ini holding text."""
    fd, path = tempfile.mkstemp(suffix='.ini')
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    cfg = Config.__new__(Config)
    cfg.config_file = path
    return cfg, path


def _read(path):
    with open(path) as f:
        return f.read()


def test_ini_replaces_existing_key_and_keeps_comments():
    cfg, path = _ini("# top\n[connection]\n# why\nactive_reconnect = true\n"
                     "reconnect_delay = 5\n\n[device]\nname = K\n")
    assert cfg.set_active_reconnect(False)
    assert _read(path) == ("# top\n[connection]\n# why\nactive_reconnect = false\n"
                           "reconnect_delay = 5\n\n[device]\nname = K\n")
    assert cfg.active_reconnect is False


def test_ini_adds_key_at_end_of_section():
    cfg, path = _ini("[connection]\nreconnect_delay = 5\n\n[device]\nname = K\n")
    cfg._write_ini_option('connection', 'active_reconnect', 'false')
    assert _read(path) == ("[connection]\nreconnect_delay = 5\n"
                           "active_reconnect = false\n\n[device]\nname = K\n")


def test_ini_adds_key_to_last_section():
    cfg, path = _ini("[device]\n[connection]\nreconnect_delay = 5")
    cfg._write_ini_option('connection', 'active_reconnect', 'true')
    assert _read(path) == "[device]\n[connection]\nreconnect_delay = 5\nactive_reconnect = true\n"


def test_ini_adds_missing_section():
    cfg, path = _ini("[device]\nname = K\n")
    cfg._write_ini_option('connection', 'active_reconnect', 'false')
    assert _read(path) == "[device]\nname = K\n\n[connection]\nactive_reconnect = false\n"


def test_ini_ignores_commented_key():
    cfg, path = _ini("[connection]\n# active_reconnect = true\n")
    cfg._write_ini_option('connection', 'active_reconnect', 'false')
    assert _read(path) == "[connection]\n# active_reconnect = true\nactive_reconnect = false\n"


class _Dev:
    def __init__(self, address):
        self.address = address


class _Device:
    def __init__(self):
        self.pages = 0

    async def connect(self, target, transport=None):
        self.pages += 1
        raise ConnectionError("hci/PAGE_TIMEOUT_ERROR")


class _Host(classic.ClassicMixin):
    ACTIVE_DELAY = 0
    ACTIVE_RETRY_INTERVAL = 0
    ACTIVE_RETRY_INTERVAL_CONNECTED = 0
    ACTIVE_CONNECT_TIMEOUT = 10

    def __init__(self):
        self.classic_devices = [_Dev('AA:BB:CC:DD:EE:01'), _Dev('AA:BB:CC:DD:EE:02')]
        self.sessions = {}
        self.device = _Device()
        self._radio_lock = asyncio.Lock()

    def _format_device(self, addr):
        return addr


def _pages_after(enabled, passes):
    """Run the paging loop for a few idle passes, counting pages sent."""
    host = _Host()
    real_sleep = asyncio.sleep
    saved = (config.active_reconnect, classic.Address, classic.asyncio.sleep)
    calls = 0

    async def fast_sleep(_delay):
        nonlocal calls
        calls += 1
        if calls > passes:
            raise asyncio.CancelledError
        await real_sleep(0)

    config.active_reconnect = enabled
    classic.Address = type('Address', (), {
        'PUBLIC_DEVICE_ADDRESS': 0,
        '__init__': lambda self, addr, kind=None: None})
    classic.asyncio.sleep = fast_sleep
    try:
        asyncio.run(host._classic_active_connect_loop())
    except asyncio.CancelledError:
        pass
    finally:
        config.active_reconnect, classic.Address, classic.asyncio.sleep = saved
    return host.device.pages


def test_loop_keeps_paging_when_on():
    assert _pages_after(True, 20) > 4


def test_loop_pages_once_per_start_when_off():
    assert _pages_after(False, 20) == 2


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
