from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from .recorder import SessionRecorder
from .store import MemoryStore

log = logging.getLogger("multiagents")

# LLM extraction prompt sent to Haiku
_EXTRACTION_PROMPT = """\
Given this multi-agent discussion transcript summary, extract learnings.

Session query: {query}
Agents: {agents}
Rounds: {rounds}, Converged: {converged}

Per-agent stats:
{per_agent_stats}

Agent responses (key excerpts):
{excerpts}

Extract as JSON (no markdown fences):
{{
  "per_agent": {{
    "agent_name": {{
      "strengths": [".."],
      "weaknesses": [".."],
      "notable_behaviors": [".."],
      "role_effectiveness": {{"coordinator": 0.0, "implementer": 0.0, "reviewer": 0.0}}
    }}
  }},
  "session_learnings": ["what went well", "what could improve"],
  "tags": ["converged", "good-coordination"]
}}
"""


class MemoryManager:
    def __init__(self, project_root: Path, extraction_model: str = "haiku") -> None:
        self.project_root = project_root
        self.extraction_model = extraction_model
        self.store = MemoryStore(project_root)

    # -- Context building (called once per session) ----------------------------

    def build_memory_context(self, query: str, limit: int = 5) -> str:
        sections: list[str] = []

        # Section 1: Agent capability profiles
        profiles = self.store.get_agent_profiles()
        if profiles:
            lines = ["### Agent Capabilities (from past sessions)"]
            for p in profiles:
                parts = [f"**{p['agent_name'].title()}**"]
                if p["best_role"]:
                    parts.append(f"Best role: {p['best_role']}")
                if p["strengths"]:
                    parts.append(f"Strengths: {', '.join(p['strengths'][:3])}")
                if p["avg_response_time_ms"] > 0:
                    parts.append(f"Avg response: {p['avg_response_time_ms']:.1f}ms")
                if p["notable_behaviors"]:
                    parts.append(f"Notes: {p['notable_behaviors'][0]}")
                lines.append(f"- {'. '.join(parts)}.")
            sections.append("\n".join(lines))

        # Section 2: Ensemble collaboration patterns
        patterns = self.store.get_ensemble_patterns(category="combo")
        if patterns:
            lines = ["### Collaboration Notes"]
            for pat in patterns:
                val = pat["value"]
                if isinstance(val, dict):
                    combo = pat["key"]
                    sess = val.get("sessions", 0)
                    conv = val.get("convergence_rate", 0)
                    avg_r = val.get("avg_rounds", 0)
                    lines.append(
                        f"- {combo}: {sess} sessions, {conv:.0%} convergence, avg {avg_r:.1f} rounds"
                    )
            sections.append("\n".join(lines))

        # Section 3: Relevant past episodes (keyword search)
        if query.strip():
            episodes = self.store.search_episodes(query, limit=limit)
            if episodes:
                lines = ["### Relevant Past Discussions"]
                for ep in episodes:
                    agents_str = ", ".join(ep["agents"]) if ep["agents"] else "unknown"
                    conv = "converged" if ep["converged"] else "did not converge"
                    lines.append(
                        f"- **{ep['query'][:80]}** ({agents_str}, {ep['rounds']} rounds, {conv})"
                    )
                sections.append("\n".join(lines))

        if not sections:
            return ""
        return "## Agent Knowledge\n\n" + "\n\n".join(sections)

    # -- Session finalization ---------------------------------------------------

    def finalize_session(self, session_id: str) -> str | None:
        transcript_path = (
            self.project_root / ".multiagents" / "transcripts" / f"{session_id}.jsonl"
        )
        if not transcript_path.exists():
            return None
        if self.store.episode_exists_for_session(session_id):
            return None
        events = SessionRecorder.read_transcript(transcript_path)
        if not events:
            return None

        # Parse transcript into structured stats
        stats = self._parse_transcript(events)

        # Extract learnings (LLM or heuristic fallback)
        learnings = self._extract_learnings(stats)

        # Save the episode
        ep_id = self.store.save_episode(
            session_id=session_id,
            query=stats["query"],
            summary=stats["summary"],
            rounds=stats["rounds"],
            converged=stats["converged"],
            duration_ms=stats["duration_ms"],
            agents=sorted(stats["agents"]),
            tags=learnings.get("tags", []),
            transcript_path=str(transcript_path),
        )

        # Save per-agent episodes and update profiles
        for agent_name, agent_stats in stats["per_agent"].items():
            self.store.save_agent_episode(
                episode_id=ep_id,
                agent_name=agent_name,
                response_time_ms=int(agent_stats.get("total_latency_ms", 0)),
                agreed_with_consensus=agent_stats.get("agreements", 0) > 0,
                unique_contributions=agent_stats.get("excerpts", []),
            )
            # Merge LLM learnings into profile update
            agent_learnings = learnings.get("per_agent", {}).get(agent_name, {})
            self._update_agent_profile(agent_name, agent_stats, agent_learnings)

        # Update ensemble patterns
        self._update_ensemble_patterns(stats)

        return ep_id

    # -- Transcript parsing (heuristic) ----------------------------------------

    @staticmethod
    def _parse_transcript(events: list[dict]) -> dict:
        user_messages: list[str] = []
        agents_seen: set[str] = set()
        total_rounds = 0
        converged = False
        total_duration_ms = 0.0

        per_agent: dict[str, dict] = {}

        for ev in events:
            t = ev.get("type", "")
            d = ev.get("data", {})

            if t == "user_message":
                user_messages.append(d.get("text", ""))

            elif t == "agent_completed":
                agent = d.get("agent", "")
                if not agent:
                    continue
                agents_seen.add(agent)
                latency = d.get("latency_ms", 0)
                total_duration_ms += latency
                passed = d.get("passed", False)
                text = d.get("text", "")
                rnd = d.get("round", 0)

                if agent not in per_agent:
                    per_agent[agent] = {
                        "active_rounds": 0,
                        "pass_rounds": 0,
                        "total_latency_ms": 0.0,
                        "latency_samples": 0,
                        "agreements": 0,
                        "mentions": 0,
                        "used_share_tags": False,
                        "excerpts": [],
                        "first_response": "",
                        "last_response": "",
                    }

                s = per_agent[agent]
                s["total_latency_ms"] += latency
                s["latency_samples"] += 1

                if passed:
                    s["pass_rounds"] += 1
                else:
                    s["active_rounds"] += 1
                    # Track excerpts (first and last substantive response)
                    if not s["first_response"]:
                        s["first_response"] = text[:300]
                    s["last_response"] = text[:300]
                    if text not in s["excerpts"] and len(s["excerpts"]) < 3:
                        s["excerpts"].append(text[:200])

                # Detect agreements (+1, agree, etc.)
                lower = text.lower()
                if "+1" in lower or "agree" in lower or "good point" in lower:
                    s["agreements"] += 1

                # Detect mentions (@AgentName)
                for other_agent in agents_seen:
                    if f"@{other_agent}" in text.lower():
                        s["mentions"] += 1

                # Detect share tag usage
                if "<share>" in text.lower():
                    s["used_share_tags"] = True

            elif t == "discussion_ended":
                total_rounds = d.get("rounds", 0)
                reason = d.get("reason", "")
                converged = reason == "all_passed" or d.get("all_passed", False)

        query = user_messages[0][:300] if user_messages else ""

        # Build summary from first responses
        parts = []
        for agent_name in sorted(agents_seen):
            s = per_agent.get(agent_name, {})
            first = s.get("first_response", "")
            if first:
                parts.append(f"{agent_name}: {first[:200]}")
        summary = "; ".join(parts) if parts else "Empty discussion"

        return {
            "query": query,
            "summary": summary,
            "rounds": total_rounds,
            "converged": converged,
            "duration_ms": int(total_duration_ms),
            "agents": agents_seen,
            "per_agent": per_agent,
        }

    # -- Learning extraction ---------------------------------------------------

    def _extract_learnings(self, stats: dict) -> dict:
        """Try LLM extraction via claude CLI first, fall back to heuristic."""
        if shutil.which("claude"):
            try:
                return self._extract_learnings_llm(stats)
            except Exception:
                log.debug("claude CLI extraction failed, falling back to heuristic", exc_info=True)
        return self._extract_learnings_heuristic(stats)

    def _extract_learnings_llm(self, stats: dict) -> dict:
        # Build per-agent stats string
        agent_lines = []
        for name, s in stats["per_agent"].items():
            avg_lat = s["total_latency_ms"] / max(s["latency_samples"], 1)
            agent_lines.append(
                f"- {name}: {s['active_rounds']} active, {s['pass_rounds']} pass, "
                f"avg {avg_lat:.0f}ms, {s['mentions']} mentions, {s['agreements']} agreements, "
                f"Share tags: {'yes' if s['used_share_tags'] else 'no'}"
            )

        # Build excerpts
        excerpt_lines = []
        for name, s in stats["per_agent"].items():
            if s.get("first_response"):
                excerpt_lines.append(f"[{name} first]: {s['first_response'][:200]}")
            if s.get("last_response") and s["last_response"] != s.get("first_response"):
                excerpt_lines.append(f"[{name} last]: {s['last_response'][:200]}")

        prompt = _EXTRACTION_PROMPT.format(
            query=stats["query"][:200],
            agents=", ".join(sorted(stats["agents"])),
            rounds=stats["rounds"],
            converged="yes" if stats["converged"] else "no",
            per_agent_stats="\n".join(agent_lines),
            excerpts="\n".join(excerpt_lines) or "(no excerpts)",
        )

        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--verbose",
                "--output-format", "stream-json",
                "--model", self.extraction_model,
                "--max-turns", "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI exited {result.returncode}: {result.stderr[:200]}")

        # Parse stream-json JSONL to find the result object
        text = ""
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "result":
                text = obj.get("result", "")
                break

        if not text:
            raise RuntimeError("no result in claude CLI output")
        return json.loads(text)

    @staticmethod
    def _extract_learnings_heuristic(stats: dict) -> dict:
        """Heuristic fallback when no API key is available."""
        per_agent: dict[str, dict] = {}
        tags: list[str] = []

        if stats["converged"]:
            tags.append("converged")
        if stats["rounds"] <= 2:
            tags.append("quick-resolution")
        elif stats["rounds"] >= 5:
            tags.append("extended-discussion")

        for name, s in stats["per_agent"].items():
            strengths: list[str] = []
            weaknesses: list[str] = []
            behaviors: list[str] = []
            roles: dict[str, float] = {"coordinator": 0.0, "implementer": 0.0, "reviewer": 0.0}

            total_rounds = s["active_rounds"] + s["pass_rounds"]
            active_ratio = s["active_rounds"] / max(total_rounds, 1)
            avg_lat = s["total_latency_ms"] / max(s["latency_samples"], 1)

            # Heuristic role scoring
            if s["mentions"] > 0:
                roles["coordinator"] = min(1.0, s["mentions"] / max(total_rounds, 1))
                strengths.append("active communicator")
            if active_ratio > 0.7:
                roles["implementer"] = active_ratio
                strengths.append("thorough contributor")
            if s["agreements"] > 0:
                roles["reviewer"] = min(1.0, s["agreements"] / max(s["active_rounds"], 1))
                strengths.append("collaborative")

            if s["pass_rounds"] > s["active_rounds"]:
                behaviors.append("often passes (conservative)")
            if avg_lat < 5000 and s["latency_samples"] > 0:
                strengths.append("fast responses")
            elif avg_lat > 30000 and s["latency_samples"] > 0:
                weaknesses.append("slow responses")
            if s["used_share_tags"]:
                behaviors.append("uses Share tags")

            per_agent[name] = {
                "strengths": strengths,
                "weaknesses": weaknesses,
                "notable_behaviors": behaviors,
                "role_effectiveness": roles,
            }

        session_learnings = []
        if stats["converged"]:
            session_learnings.append("Discussion converged successfully")
        else:
            session_learnings.append("Discussion did not converge")

        return {
            "per_agent": per_agent,
            "session_learnings": session_learnings,
            "tags": tags,
        }

    # -- Profile update (cross-session aggregation) ----------------------------

    def _update_agent_profile(
        self,
        agent_name: str,
        agent_stats: dict,
        agent_learnings: dict,
    ) -> None:
        """Merge new session data into the agent's cross-session profile."""
        existing = self.store.get_agent_profiles([agent_name])
        profile = existing[0] if existing else None

        new_strengths = agent_learnings.get("strengths", [])
        new_weaknesses = agent_learnings.get("weaknesses", [])
        new_behaviors = agent_learnings.get("notable_behaviors", [])
        new_roles = agent_learnings.get("role_effectiveness", {})

        avg_lat = agent_stats["total_latency_ms"] / max(agent_stats["latency_samples"], 1)
        total_active = agent_stats["active_rounds"]
        agreements = agent_stats["agreements"]

        if profile:
            n = profile["total_sessions"]
            # Running average for response time
            merged_avg_lat = (profile["avg_response_time_ms"] * n + avg_lat) / (n + 1)
            # Merge lists (deduplicate, keep recent)
            merged_strengths = _merge_list(profile["strengths"], new_strengths, max_items=5)
            merged_weaknesses = _merge_list(profile["weaknesses"], new_weaknesses, max_items=5)
            merged_behaviors = _merge_list(profile["notable_behaviors"], new_behaviors, max_items=5)
            # Merge role scores (running average)
            merged_roles = dict(profile["role_scores"])
            for role, score in new_roles.items():
                old = merged_roles.get(role, 0.0)
                merged_roles[role] = (old * n + score) / (n + 1)
            # Consensus rate
            old_agree = profile["consensus_agreement_rate"]
            new_agree = 1.0 if agreements > 0 else 0.0
            merged_agree = (old_agree * n + new_agree) / (n + 1)
            total_sessions = n + 1
        else:
            merged_avg_lat = avg_lat
            merged_strengths = new_strengths[:5]
            merged_weaknesses = new_weaknesses[:5]
            merged_behaviors = new_behaviors[:5]
            merged_roles = new_roles
            merged_agree = 1.0 if agreements > 0 else 0.0
            total_sessions = 1

        # Determine best role
        best_role = ""
        if merged_roles:
            best_role = max(merged_roles, key=lambda k: merged_roles[k])

        self.store.update_agent_profile(
            agent_name=agent_name,
            strengths=merged_strengths,
            weaknesses=merged_weaknesses,
            notable_behaviors=merged_behaviors,
            avg_response_time_ms=merged_avg_lat,
            consensus_agreement_rate=merged_agree,
            role_scores=merged_roles,
            best_role=best_role,
            total_sessions=total_sessions,
        )

    # -- Ensemble pattern update -----------------------------------------------

    def _update_ensemble_patterns(self, stats: dict) -> None:
        """Update agent combination statistics."""
        agents = sorted(stats["agents"])
        if len(agents) < 2:
            return
        combo_key = " + ".join(a.title() for a in agents)

        existing = self.store.get_ensemble_patterns(category="combo")
        current = None
        for pat in existing:
            if pat["key"] == combo_key:
                current = pat["value"]
                break

        if current and isinstance(current, dict):
            n = current.get("sessions", 0)
            old_conv = current.get("convergence_rate", 0.0)
            old_avg_r = current.get("avg_rounds", 0.0)
            new_conv = 1.0 if stats["converged"] else 0.0
            merged_conv = (old_conv * n + new_conv) / (n + 1)
            merged_avg_r = (old_avg_r * n + stats["rounds"]) / (n + 1)
            value = {
                "sessions": n + 1,
                "convergence_rate": merged_conv,
                "avg_rounds": merged_avg_r,
            }
        else:
            value = {
                "sessions": 1,
                "convergence_rate": 1.0 if stats["converged"] else 0.0,
                "avg_rounds": float(stats["rounds"]),
            }

        self.store.save_ensemble_pattern(combo_key, "combo", value)

    # -- Pending transcript recovery -------------------------------------------

    def get_pending_transcripts(self) -> list[Path]:
        transcript_dir = self.project_root / ".multiagents" / "transcripts"
        if not transcript_dir.exists():
            return []
        pending = []
        for path in sorted(transcript_dir.glob("*.jsonl")):
            if not self.store.episode_exists_for_session(path.stem):
                pending.append(path)
        return pending


def _merge_list(old: list[str], new: list[str], max_items: int = 5) -> list[str]:
    """Merge two lists, deduplicating and keeping up to max_items."""
    seen: set[str] = set()
    result: list[str] = []
    for item in new + old:
        lower = item.lower()
        if lower not in seen:
            seen.add(lower)
            result.append(item)
        if len(result) >= max_items:
            break
    return result
