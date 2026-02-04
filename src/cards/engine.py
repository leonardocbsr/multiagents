"""CardEngine: lifecycle management and prompt generation for task cards."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from .models import Card, CardPhaseEntry, CardStatus

# ---------------------------------------------------------------------------
# [DONE] detection  (mirrors detect_pass in src/chat/router.py but for [DONE])
# ---------------------------------------------------------------------------

_DONE_RE = re.compile(r"\[DONE\]", re.IGNORECASE)


def detect_done(text: str) -> bool:
    """Return True if *text* contains a [DONE] marker (case-insensitive)."""
    return bool(_DONE_RE.search(text))


# ---------------------------------------------------------------------------
# Delegation response parsing
# ---------------------------------------------------------------------------

_ROLE_PATTERN = re.compile(
    r"(?:coordinator|planner|implementer|reviewer)\s*:\s*@(\w+)", re.IGNORECASE
)


def _parse_roles(text: str) -> dict[str, str]:
    """Extract role -> agent mappings from a block of text.

    Looks for patterns like ``Planner: @Claude``.
    Returns e.g. ``{"planner": "claude", "implementer": "codex", "reviewer": "kimi"}``.
    Keys are lower-cased role names; values are lower-cased agent names.
    """
    roles: dict[str, str] = {}
    for match in re.finditer(
        r"(coordinator|planner|implementer|reviewer)\s*:\s*@(\w+)", text, re.IGNORECASE
    ):
        role = match.group(1).lower()
        agent = match.group(2).lower()
        roles[role] = agent
    return roles


# ---------------------------------------------------------------------------
# CardEngine
# ---------------------------------------------------------------------------


class CardEngine:
    """Manages the card lifecycle and generates prompts for each phase."""

    def __init__(self, agents: list[str]) -> None:
        self._agents = [a.lower() for a in agents]
        self._cards: dict[str, Card] = {}

    # -- CRUD ---------------------------------------------------------------

    def create_card(
        self,
        title: str,
        description: str,
        planner: str = "",
        implementer: str = "",
        reviewer: str = "",
        coordinator: str = "",
    ) -> Card:
        card = Card(
            id=uuid.uuid4().hex[:12],
            title=title,
            description=description,
            status=CardStatus.BACKLOG,
            planner=planner.lower() if planner else "",
            implementer=implementer.lower() if implementer else "",
            reviewer=reviewer.lower() if reviewer else "",
            coordinator=coordinator.lower() if coordinator else "",
            coordination_stage="",
            previous_phase=None,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._cards[card.id] = card
        return card

    def update_card(self, card_id: str, **fields: object) -> Card:
        card = self._get(card_id)
        for key, value in fields.items():
            if not hasattr(card, key):
                raise ValueError(f"Card has no field '{key}'")
            if key in ("status", "previous_phase") and isinstance(value, str):
                value = CardStatus(value)
            setattr(card, key, value)
        return card

    def delete_card(self, card_id: str) -> None:
        self._get(card_id)  # raises if missing
        del self._cards[card_id]

    def get_card(self, card_id: str) -> Card:
        return self._get(card_id)

    def get_cards(self) -> list[Card]:
        return list(self._cards.values())

    def load_cards(self, cards: list[Card]) -> None:
        """Populate the engine from a list of persisted Card objects."""
        for card in cards:
            self._cards[card.id] = card

    def get_cards_for_agent(self, agent_name: str) -> list[Card]:
        name = agent_name.lower()
        return [
            c
            for c in self._cards.values()
            if name in (c.planner, c.implementer, c.reviewer, c.coordinator)
        ]

    # -- Lifecycle ----------------------------------------------------------

    def start_card(self, card_id: str) -> tuple[Card, str]:
        """Transition backlog -> planning (or coordinating if coordinator set)."""
        card = self._get(card_id)
        if card.status != CardStatus.BACKLOG:
            raise ValueError(
                f"Can only start a card in backlog (current: {card.status.value})"
            )
        if card.coordinator:
            card.status = CardStatus.COORDINATING
            card.coordination_stage = "initial"
            card.previous_phase = None
            prompt = self._build_coordinating_prompt(card)
            return card, prompt
        card.status = CardStatus.PLANNING
        card.previous_phase = None
        prompt = self._build_planning_prompt(card)
        return card, prompt

    def on_agent_completed(
        self, card_id: str, agent: str, content: str
    ) -> tuple[Card, str | None]:
        """Called when a card-phase round ends.

        Appends a history entry, then:
        - If the card is in a *work* phase (planning / implementing) and [DONE]
          is detected, transition to reviewing and return a review prompt.
        - If the card is in reviewing:
            - [DONE] after planning  -> move to implementing, return impl prompt.
            - [DONE] after implementing -> stay in reviewing, return None (user
              decides when to mark done).
            - No [DONE] -> reject back to previous phase with feedback.
        """
        card = self._get(card_id)
        entry = CardPhaseEntry(
            phase=card.status,
            agent=agent.lower(),
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        card.history.append(entry)

        done = detect_done(content)

        # --- Coordinating phase --------------------------------------------
        if card.status == CardStatus.COORDINATING:
            if card.coordination_stage == "initial":
                if done:
                    roles = _parse_roles(content)
                    for role, agent in roles.items():
                        if hasattr(card, role):
                            setattr(card, role, agent)
                    card.status = CardStatus.PLANNING
                    card.coordination_stage = ""
                    return card, self._build_planning_prompt(card)
                return card, None

            if card.coordination_stage == "plan_decision":
                if done:
                    card.status = CardStatus.IMPLEMENTING
                    card.coordination_stage = ""
                    return card, self._build_implementation_prompt(card)
                card.status = CardStatus.PLANNING
                card.coordination_stage = ""
                return card, self._build_rejection_prompt(card, content)

            if card.coordination_stage == "impl_decision":
                if done:
                    card.status = CardStatus.DONE
                    card.coordination_stage = ""
                    return card, None
                card.status = CardStatus.IMPLEMENTING
                card.coordination_stage = ""
                return card, self._build_rejection_prompt(card, content)

            return card, None

        # --- Work phases: planning / implementing ---------------------------
        if card.status in (CardStatus.PLANNING, CardStatus.IMPLEMENTING):
            if done:
                previous = card.status
                card.previous_phase = previous
                card.status = CardStatus.REVIEWING
                prompt = self._build_review_prompt(card, content)
                return card, prompt
            # Not done yet -- no transition, no new prompt
            return card, None

        # --- Reviewing phase ------------------------------------------------
        if card.status == CardStatus.REVIEWING:
            if card.coordinator:
                # Route ALL reviewer output to coordinator for decision
                stage = "plan_decision" if card.previous_phase == CardStatus.PLANNING else "impl_decision"
                card.status = CardStatus.COORDINATING
                card.coordination_stage = stage
                prompt = self._build_coordination_decision_prompt(card, content)
                return card, prompt
            if done:
                if card.previous_phase == CardStatus.PLANNING:
                    card.status = CardStatus.IMPLEMENTING
                    prompt = self._build_implementation_prompt(card)
                    return card, prompt
                # previous_phase == IMPLEMENTING -> wait for user
                return card, None
            # Rejection: send back to previous phase
            previous = card.previous_phase or CardStatus.PLANNING
            card.status = previous
            card.previous_phase = None
            prompt = self._build_rejection_prompt(card, content)
            return card, prompt

        return card, None

    def mark_done(self, card_id: str) -> Card:
        """User-triggered.  Moves reviewing -> done."""
        card = self._get(card_id)
        if card.status != CardStatus.REVIEWING:
            raise ValueError(
                f"Can only mark done from reviewing (current: {card.status.value})"
            )
        card.status = CardStatus.DONE
        return card

    # -- Delegation ---------------------------------------------------------

    def build_delegation_prompt(self, card_id: str) -> str:
        card = self._get(card_id)
        agents_str = ", ".join(self._agents)
        return (
            f'A new task needs role assignments: "{card.title}"\n\n'
            f"Description: {card.description}\n\n"
            f"Available agents: {agents_str}\n\n"
            "Which of you should be the coordinator (tech lead), planner, implementer, and reviewer? "
            "Discuss and use @AgentName tags to assign roles. "
            "Coordinator is optional but recommended for complex tasks. "
            'Example: "Coordinator: @Claude, Planner: @Claude, Implementer: @Codex, Reviewer: @Kimi"'
        )

    def parse_delegation_response(
        self, card_id: str, agent_responses: dict[str, str]
    ) -> Card | None:
        """Parse role claims from agent responses.

        Merges all responses and looks for Planner/Implementer/Reviewer
        assignments.  Returns the updated card if all three roles are found,
        otherwise ``None``.
        """
        card = self._get(card_id)
        combined = "\n".join(agent_responses.values())
        roles = _parse_roles(combined)

        if all(k in roles for k in ("planner", "implementer", "reviewer")):
            card.planner = roles["planner"]
            card.implementer = roles["implementer"]
            card.reviewer = roles["reviewer"]
            if "coordinator" in roles:
                card.coordinator = roles["coordinator"]
            return card
        return None

    # -- Internal helpers ---------------------------------------------------

    def _get(self, card_id: str) -> Card:
        try:
            return self._cards[card_id]
        except KeyError:
            raise KeyError(f"Card not found: {card_id}") from None

    @staticmethod
    def _get_latest_output(card: Card, phase: CardStatus) -> str | None:
        """Return the content of the most recent history entry for *phase*."""
        for entry in reversed(card.history):
            if entry.phase == phase:
                return entry.content
        return None

    # -- Prompt builders ----------------------------------------------------

    def _build_coordinating_prompt(self, card: Card) -> str:
        """Prompt for the initial COORDINATING phase."""
        roles_status: list[str] = []
        for role in ("planner", "implementer", "reviewer"):
            agent = getattr(card, role, "")
            roles_status.append(f"  {role}: {agent or 'unassigned'}")
        roles_block = "\n".join(roles_status)
        assign_hint = ""
        if not card.planner or not card.implementer or not card.reviewer:
            assign_hint = (
                "\n\nSome roles are unassigned. Assign them using "
                '"Planner: @Agent, Implementer: @Agent, Reviewer: @Agent" syntax.'
            )
        return (
            f'[TASK:{card.id}] @{card.coordinator} You are the COORDINATOR (tech lead) for "{card.title}".\n\n'
            f"{card.description}\n\n"
            f"Current role assignments:\n{roles_block}\n"
            f"{assign_hint}\n\n"
            "Set the technical direction and approach for this task. "
            "Outline the high-level strategy the planner should follow.\n"
            "Use [DONE] when your direction is set and you're ready for planning to begin."
        )

    def _build_coordination_decision_prompt(self, card: Card, review_content: str) -> str:
        """Prompt for coordinator to make plan_decision or impl_decision."""
        if card.coordination_stage == "plan_decision":
            worker_output = self._get_latest_output(card, CardStatus.PLANNING) or ""
            return (
                f'[TASK:{card.id}] @{card.coordinator} As COORDINATOR for "{card.title}", review the plan and feedback.\n\n'
                f"Planner ({card.planner}) produced:\n{worker_output}\n\n"
                f"Reviewer ({card.reviewer}) feedback:\n{review_content}\n\n"
                "As tech lead, decide: approve with [DONE] to proceed to implementation, "
                "or provide your feedback to send the plan back for revision."
            )
        # impl_decision
        worker_output = self._get_latest_output(card, CardStatus.IMPLEMENTING) or ""
        return (
            f'[TASK:{card.id}] @{card.coordinator} As COORDINATOR for "{card.title}", review the implementation and feedback.\n\n'
            f"Implementer ({card.implementer}) produced:\n{worker_output}\n\n"
            f"Reviewer ({card.reviewer}) feedback:\n{review_content}\n\n"
            "As tech lead, decide: approve with [DONE] to mark the task complete, "
            "or provide your feedback to send it back for revision."
        )

    def _build_planning_prompt(self, card: Card) -> str:
        coordinator_block = ""
        if card.coordinator:
            approach = self._get_latest_output(card, CardStatus.COORDINATING)
            if approach:
                coordinator_block = (
                    f"\n\nCOORDINATOR DIRECTION (from @{card.coordinator} — you MUST follow this approach):\n"
                    f"{approach}\n"
                )
        return (
            f'[TASK:{card.id}] @{card.planner} You are the PLANNER for "{card.title}".\n\n'
            f"{card.description}\n"
            f"{coordinator_block}\n"
            "Plan the implementation: break it into steps, identify risks, and define acceptance criteria.\n"
            + (
                f"Your plan MUST align with the coordinator's direction above. "
                f"If you disagree, explain why — but do not deviate without @{card.coordinator}'s approval.\n"
                if card.coordinator else ""
            )
            + "Use [DONE] when your plan is complete."
        )

    def _build_review_prompt(self, card: Card, content: str) -> str:
        if card.previous_phase == CardStatus.PLANNING:
            return (
                f'[TASK:{card.id}] @{card.reviewer} You are the REVIEWER for "{card.title}".\n\n'
                f"The planner ({card.planner}) produced this plan:\n\n"
                f"{content}\n\n"
                "Review it. If the plan is solid, respond with [DONE]. "
                "Otherwise, provide specific feedback on what needs to change."
            )
        # After implementation
        plan = self._get_latest_output(card, CardStatus.PLANNING) or ""
        return (
            f'[TASK:{card.id}] @{card.reviewer} You are the REVIEWER for "{card.title}".\n\n'
            f"The implementer ({card.implementer}) produced:\n\n"
            f"{content}\n\n"
            f"Original plan:\n{plan}\n\n"
            "Review the implementation against the plan. "
            "If it meets acceptance criteria, respond with [DONE]. "
            "Otherwise, provide specific feedback."
        )

    def _build_implementation_prompt(self, card: Card) -> str:
        plan = self._get_latest_output(card, CardStatus.PLANNING) or ""
        feedback = self._get_latest_output(card, CardStatus.REVIEWING)
        feedback_block = ""
        if feedback:
            feedback_block = f"\nPrevious reviewer feedback:\n{feedback}\n"
        coordinator_block = ""
        if card.coordinator:
            approach = self._get_latest_output(card, CardStatus.COORDINATING)
            if approach:
                coordinator_block = (
                    f"\nCOORDINATOR DIRECTION (from @{card.coordinator} — you MUST follow this approach):\n"
                    f"{approach}\n"
                )
        return (
            f'[TASK:{card.id}] @{card.implementer} You are the IMPLEMENTER for "{card.title}".\n\n'
            f"Here is the approved plan:\n{plan}\n"
            f"{coordinator_block}"
            f"{feedback_block}\n"
            "Implement according to the plan"
            + (f" and the coordinator's direction" if card.coordinator else "")
            + ". Use [DONE] when implementation is complete."
        )

    def _build_rejection_prompt(self, card: Card, feedback: str) -> str:
        # Determine who is being addressed and what their previous output was
        if card.status == CardStatus.PLANNING:
            agent = card.planner
            previous_output = self._get_latest_output(card, CardStatus.PLANNING) or ""
        else:
            agent = card.implementer
            previous_output = (
                self._get_latest_output(card, CardStatus.IMPLEMENTING) or ""
            )
        source = "coordinator" if card.coordinator else "reviewer"
        return (
            f'[TASK:{card.id}] @{agent} The {source} sent back your work on "{card.title}" with feedback:\n\n'
            f"{feedback}\n\n"
            f"Previous output:\n{previous_output}\n\n"
            "Address the feedback. Use [DONE] when ready for re-review."
        )
