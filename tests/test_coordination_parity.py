"""Parity tests validating Python coordination extractors against the shared fixture.

The fixture at tests/fixtures/coordination_patterns.json is the canonical
specification for coordination pattern regexes shared between:
  - Python: src/chat/router.py
  - TypeScript: web/src/types.ts

Status expected values use Python's case-preserving behavior.
TypeScript normalizes to uppercase via .toUpperCase() for display.
"""

import json
from pathlib import Path

import pytest

from src.chat.router import (
    extract_agreements,
    extract_handoffs,
    extract_mentions,
    extract_statuses,
)

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "coordination_patterns.json").read_text()
)


@pytest.mark.parametrize(
    "case", _FIXTURE["mentions"], ids=[c["input"][:40] for c in _FIXTURE["mentions"]]
)
def test_mentions(case: dict) -> None:
    assert extract_mentions(case["input"]) == case["expected"]


@pytest.mark.parametrize(
    "case", _FIXTURE["agreements"], ids=[c["input"][:40] for c in _FIXTURE["agreements"]]
)
def test_agreements(case: dict) -> None:
    assert extract_agreements(case["input"]) == case["expected"]


@pytest.mark.parametrize(
    "case", _FIXTURE["handoffs"], ids=[c["input"][:40] for c in _FIXTURE["handoffs"]]
)
def test_handoffs(case: dict) -> None:
    result = extract_handoffs(case["input"])
    expected = [(h["agent"], h["context"]) for h in case["expected"]]
    assert result == expected


@pytest.mark.parametrize(
    "case", _FIXTURE["statuses"], ids=[c["input"][:40] for c in _FIXTURE["statuses"]]
)
def test_statuses(case: dict) -> None:
    assert extract_statuses(case["input"]) == case["expected"]
