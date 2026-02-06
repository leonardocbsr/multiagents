from __future__ import annotations

from src.allowlist import is_allowed


def test_allowed_user():
    allowlist = {111, 222, 333}
    assert is_allowed(222, allowlist) is True


def test_disallowed_user():
    allowlist = {111, 222, 333}
    assert is_allowed(999, allowlist) is False


def test_empty_allowlist():
    assert is_allowed(111, set()) is False
