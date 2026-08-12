"""
Mode controller, after "A Modular Mode-Switching Architecture for a
Mythic-Logic Companion" (§5, §6) and the boot block's Modes clause.

Four modes, resolved in a fixed order:

    1. an explicit override phrase in the user's line
    2. an implicit hard-reality trigger  -- priority 100, always wins
    3. an implicit trigger for any other mode
    4. the mode already running

The point of assigning priority in advance is that the system is never in
the position of guessing which behaviour to believe after a conflict has
already arisen. hard_reality_mode is the one that overrides, so it is the
one that gets decided first and cannot be talked out of by a later phrase
in the same line.

Every profile key here changes what the console does. Keys from the source
paper that this front end does not implement are absent rather than inert.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ENGINE_PATH = Path(__file__).parent / "data" / "engine.json"

HARD_REALITY = "hard_reality_mode"


@dataclass(frozen=True)
class Mode:
    name: str
    description: str
    priority: int
    tone: tuple[str, ...]
    narrative_frame: bool
    symbolic_reframing: bool
    scaffold: bool
    retrieval_status: str
    answer_without_retrieval: bool
    teach_allowed: bool
    max_related: int
    trigger_is_instruction: bool
    override_phrases: tuple[str, ...]
    implicit_triggers: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.name.replace("_mode", "").replace("_", " ")


@dataclass(frozen=True)
class Switch:
    """The result of resolving one input line."""

    mode: Mode
    previous: str
    reason: str  # 'explicit', 'implicit', 'sticky'
    trigger: str = ""

    @property
    def changed(self) -> bool:
        return self.mode.name != self.previous

    def explain(self) -> str:
        if not self.changed:
            return f"mode unchanged ({self.mode.name})"
        if self.reason == "explicit":
            return f"{self.previous} -> {self.mode.name} (you asked: '{self.trigger}')"
        return f"{self.previous} -> {self.mode.name} (topic trigger: '{self.trigger}')"


class ModeController:
    def __init__(self, config: dict | None = None, default: str | None = None):
        self.config = config or load_engine()
        self.modes: dict[str, Mode] = {
            name: _as_mode(name, profile)
            for name, profile in self.config["modes"].items()
        }
        engine = self.config.get("engine", {})
        start = default or engine.get("default_mode") or "strict_tool_mode"
        if start not in self.modes:
            raise ValueError(f"unknown mode: {start}")
        self.default = start
        self.current = self.modes[start]
        self.log: list[Switch] = []

    # -- resolution --------------------------------------------------------
    def resolve(self, line: str) -> Switch:
        """Decide which mode should answer this line, and switch to it."""
        text = line.lower()
        previous = self.current.name

        explicit = self._explicit(text)
        if explicit:
            return self._apply(explicit[0], previous, "explicit", explicit[1])

        # Priority override is checked before any other implicit trigger, so
        # "walk me through this contract" lands in hard reality, not teaching.
        for mode in sorted(self.modes.values(), key=lambda m: -m.priority):
            trigger = self._implicit(mode, text)
            if trigger:
                if mode.priority >= self.modes[HARD_REALITY].priority or mode.name != previous:
                    return self._apply(mode, previous, "implicit", trigger)
                break

        return self._apply(self.current, previous, "sticky")

    def set(self, name: str) -> Switch:
        """Switch by name, e.g. from a :mode command."""
        if name not in self.modes:
            raise KeyError(name)
        return self._apply(self.modes[name], self.current.name, "explicit", name)

    def _apply(self, mode: Mode, previous: str, reason: str, trigger: str = "") -> Switch:
        self.current = mode
        switch = Switch(mode, previous, reason, trigger)
        self.log.append(switch)
        return switch

    def _explicit(self, text: str) -> tuple[Mode, str] | None:
        best: tuple[Mode, str] | None = None
        for mode in self.modes.values():
            for phrase in mode.override_phrases:
                if phrase in text:
                    if best is None or len(phrase) > len(best[1]):
                        best = (mode, phrase)
        return best

    @staticmethod
    def _implicit(mode: Mode, text: str) -> str:
        for trigger in mode.implicit_triggers:
            if re.search(rf"(?<![a-z0-9]){re.escape(trigger)}(?![a-z0-9])", text):
                return trigger
        return ""

    # -- presentation ------------------------------------------------------
    @property
    def symbols(self) -> dict:
        return self.config.get("symbols", {})

    def describe(self, name: str | None = None) -> str:
        mode = self.modes[name] if name else self.current
        lines = [
            f"{mode.name}  (priority {mode.priority})",
            f"  {mode.description}",
            f"  tone            {', '.join(mode.tone)}",
            f"  retrieval       status = {mode.retrieval_status}",
            f"  narrative frame {_yn(mode.narrative_frame)}",
            f"  scaffolding     {_yn(mode.scaffold)}",
            f"  answers without a retrieved page  {_yn(mode.answer_without_retrieval)}",
            f"  accepts taught pages              {_yn(mode.teach_allowed)}",
        ]
        if mode.override_phrases:
            lines.append(f"  say             \"{mode.override_phrases[0]}\"")
        return "\n".join(lines)

    def table(self) -> str:
        return "\n\n".join(self.describe(name) for name in self.modes)


def load_engine(path: Path | None = None) -> dict:
    return json.loads(Path(path or ENGINE_PATH).read_text(encoding="utf-8"))


def _as_mode(name: str, profile: dict) -> Mode:
    return Mode(
        name=name,
        description=profile.get("description", ""),
        priority=int(profile.get("priority", 10)),
        tone=tuple(profile.get("tone", ())),
        narrative_frame=bool(profile.get("narrative_frame", False)),
        symbolic_reframing=bool(profile.get("symbolic_reframing", False)),
        scaffold=bool(profile.get("scaffold", False)),
        retrieval_status=profile.get("retrieval_status", "current"),
        answer_without_retrieval=bool(profile.get("answer_without_retrieval", False)),
        teach_allowed=bool(profile.get("teach_allowed", True)),
        max_related=int(profile.get("max_related", 3)),
        trigger_is_instruction=bool(profile.get("trigger_is_instruction", True)),
        override_phrases=tuple(p.lower() for p in profile.get("override_phrases", ())),
        implicit_triggers=tuple(t.lower() for t in profile.get("implicit_triggers", ())),
    )


def _yn(value: bool) -> str:
    return "yes" if value else "no"
