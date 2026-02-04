from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CardStatus(Enum):
    """Kanban phases a card flows through."""

    BACKLOG = "backlog"
    COORDINATING = "coordinating"
    PLANNING = "planning"
    REVIEWING = "reviewing"
    IMPLEMENTING = "implementing"
    DONE = "done"


@dataclass
class CardPhaseEntry:
    """A single phase-transition record in a card's history."""

    phase: CardStatus
    agent: str
    content: str
    timestamp: str


@dataclass
class Card:
    """A Kanban task card that moves through discussion phases."""

    id: str
    title: str
    description: str
    status: CardStatus
    planner: str
    implementer: str
    reviewer: str
    coordinator: str
    coordination_stage: str
    previous_phase: CardStatus | None
    history: list[CardPhaseEntry] = field(default_factory=list)
    created_at: str = ""

    @staticmethod
    def _status_str(val: CardStatus | str | None) -> str | None:
        if val is None:
            return None
        return val.value if isinstance(val, CardStatus) else str(val)

    def to_dict(self) -> dict:
        """Serialize the card for JSON / WebSocket transport."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self._status_str(self.status),
            "planner": self.planner,
            "implementer": self.implementer,
            "reviewer": self.reviewer,
            "coordinator": self.coordinator,
            "coordination_stage": self.coordination_stage,
            "previous_phase": self._status_str(self.previous_phase),
            "history": [
                {
                    "phase": self._status_str(entry.phase),
                    "agent": entry.agent,
                    "content": entry.content,
                    "timestamp": entry.timestamp,
                }
                for entry in self.history
            ],
            "created_at": self.created_at,
        }
