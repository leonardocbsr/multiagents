from __future__ import annotations


def is_allowed(user_id: int, allowlist: set[int]) -> bool:
    return user_id in allowlist
