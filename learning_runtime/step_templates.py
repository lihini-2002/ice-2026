"""Loader for step_templates.json.

Deliberately duplicates the offline pipeline's schema (see
scripts/generate_step_templates.py) instead of importing scripts/common.py —
learning_runtime has no dependency on the offline authoring pipeline (or
projectaria-tools/VRS), so it can run standalone on a mobile/edge device.

The offline schema wraps rationale/success_criteria/common_mistakes/
command_templates in a {"value", "source", "reviewed"} envelope so a human
can track review state. The runtime only cares about the value and (for
command_templates specifically) whether it's reviewed — see
command_generator.py's fallback behavior — so this loader unwraps everything
except that one reviewed flag.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _unwrap(raw: dict, key: str, empty: Any) -> Any:
    field_value = raw.get(key)
    if isinstance(field_value, dict) and "value" in field_value:
        value = field_value.get("value")
        return value if value is not None else empty
    return field_value if field_value is not None else empty


def _is_reviewed(raw: dict, key: str) -> bool:
    field_value = raw.get(key)
    return bool(field_value.get("reviewed")) if isinstance(field_value, dict) else False


@dataclass
class StepTemplate:
    step_index: int
    narration: str
    required_tools: list[str] = field(default_factory=list)
    hand_state: dict[str, list[str]] = field(default_factory=dict)  # side -> tool labels
    gaze_focus: str | None = None
    reference_frame: str | None = None
    rationale: str | None = None
    success_criteria: list[str] = field(default_factory=list)
    common_mistakes: list[dict] = field(default_factory=list)
    command_templates: dict[str, list[str]] = field(default_factory=dict)
    command_templates_reviewed: bool = False
    status: str = "needs_human_review"

    @classmethod
    def from_dict(cls, raw: dict) -> "StepTemplate":
        return cls(
            step_index=raw["step_index"],
            narration=raw.get("narration", ""),
            required_tools=list(raw.get("required_tools") or []),
            hand_state={side: list(tools) for side, tools in (raw.get("hand_state") or {}).items()},
            gaze_focus=raw.get("gaze_focus"),
            reference_frame=raw.get("reference_frame"),
            rationale=_unwrap(raw, "rationale", None),
            success_criteria=_unwrap(raw, "success_criteria", []),
            common_mistakes=_unwrap(raw, "common_mistakes", []),
            command_templates=_unwrap(raw, "command_templates", {}),
            command_templates_reviewed=_is_reviewed(raw, "command_templates"),
            status=raw.get("status", "needs_human_review"),
        )


@dataclass
class CraftTemplates:
    session_id: str
    craft: str
    task_description: str
    status: str
    steps: list[StepTemplate] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "CraftTemplates":
        raw = json.loads(Path(path).read_text())
        steps = sorted((StepTemplate.from_dict(s) for s in raw.get("steps", [])), key=lambda s: s.step_index)
        return cls(
            session_id=raw.get("session_id", ""),
            craft=raw.get("craft", ""),
            task_description=raw.get("task_description", ""),
            status=raw.get("status", "needs_human_review"),
            steps=steps,
        )

    @classmethod
    def from_steps(cls, steps: list[StepTemplate], session_id: str = "", craft: str = "", task_description: str = "") -> "CraftTemplates":
        """Build directly from a list of StepTemplate — used by tests to
        construct synthetic templates without going through a JSON file."""
        return cls(session_id=session_id, craft=craft, task_description=task_description, status="ready", steps=list(steps))
