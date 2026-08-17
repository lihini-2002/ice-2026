"""Command taxonomy + slot-filled templates + debouncing.

Command categories: orient, confirm, correct_tool, correct_motion,
correct_sequence, encourage, safety. Templates are pulled from the active
step's command_templates field, authored offline (see
scripts/generate_step_templates.py) and reviewed by a human. If that field is
empty or still unreviewed, this falls back to a generic templated sentence
built from narration_text and logs a warning — it never fails silently, and
it never delivers an unreviewed LLM-drafted command as if it were
human-approved coaching copy.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from .comparator import ComparisonResult, ComparisonState
from .step_templates import StepTemplate

logger = logging.getLogger(__name__)

# Mirrors scripts/generate_step_templates.py's COMMAND_CATEGORIES. Kept as a
# separate constant (not imported) — learning_runtime has no dependency on
# the offline authoring pipeline.
COMMAND_CATEGORIES = (
    "orient",
    "confirm",
    "correct_tool",
    "correct_motion",
    "correct_sequence",
    "encourage",
    "safety",
)

_STATE_TO_CATEGORY = {
    ComparisonState.ON_TRACK: "encourage",
    ComparisonState.WRONG_TOOL: "correct_tool",
    ComparisonState.WRONG_HAND_STATE: "correct_motion",
    ComparisonState.WRONG_SEQUENCE: "correct_sequence",
    ComparisonState.STEP_COMPLETE: "confirm",
    ComparisonState.NO_EVIDENCE: "orient",
}

_GENERIC_FALLBACKS = {
    "orient": "Get your hands back on the workbench for this step: {narration}",
    "confirm": "That matches this step — nice work: {narration}",
    "correct_tool": "Try picking up the tool for this step: {narration}",
    "correct_motion": "Adjust your hand placement for this step: {narration}",
    "correct_sequence": "Hold on — that's a different step. The current step is: {narration}",
    "encourage": "Good, keep going: {narration}",
    "safety": "Take care here: {narration}",
}


@dataclass
class Command:
    category: str
    text: str
    step_index: int


class CommandGenerator:
    def __init__(self, debounce_seconds: float = 8.0, clock: Callable[[], float] = time.monotonic):
        self.debounce_seconds = debounce_seconds
        self._clock = clock
        self._last_emitted: dict[tuple[int, str], float] = {}  # (step_index, category) -> last-emitted time

    def generate(self, comparison: ComparisonResult, step: StepTemplate) -> Command | None:
        if comparison.state == ComparisonState.NO_EVIDENCE:
            return None  # nothing actionable to say about silence

        category = _STATE_TO_CATEGORY[comparison.state]
        key = (step.step_index, category)
        now = self._clock()
        last = self._last_emitted.get(key)
        if last is not None and (now - last) < self.debounce_seconds:
            return None  # same correction for this step was just given — don't repeat every frame

        self._last_emitted[key] = now
        return Command(category=category, text=self._select_template(category, step), step_index=step.step_index)

    def _select_template(self, category: str, step: StepTemplate) -> str:
        templates = step.command_templates.get(category) if step.command_templates_reviewed else None
        if templates:
            return templates[0].format(
                narration=step.narration,
                required_tools=", ".join(step.required_tools),
                gaze_focus=step.gaze_focus or "",
            )
        logger.warning(
            "step %s: command_templates missing or unreviewed for category %r — falling back to a generic "
            "narration-based sentence instead of failing silently",
            step.step_index,
            category,
        )
        return _GENERIC_FALLBACKS[category].format(narration=step.narration)
