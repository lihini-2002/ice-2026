"""Rule-based comparator: given the current perception state and the active
step template, classify the learner's contact state as on_track /
wrong_tool / wrong_hand_state / wrong_sequence / step_complete.

Deliberately simple and explicit — no black-box model — so a developer can
step through why a given frame produced a given classification while
debugging against real footage. See step_tracker.py for the same philosophy
applied to step detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .perception import PerceptionFrame
from .step_templates import CraftTemplates, StepTemplate


class ComparisonState(str, Enum):
    ON_TRACK = "on_track"
    WRONG_TOOL = "wrong_tool"
    WRONG_HAND_STATE = "wrong_hand_state"
    WRONG_SEQUENCE = "wrong_sequence"
    STEP_COMPLETE = "step_complete"
    NO_EVIDENCE = "no_evidence"  # no hand-object contact this frame — not a failure, just no signal


@dataclass
class ComparisonResult:
    state: ComparisonState
    detail: str
    matched_tools: set[str] = field(default_factory=set)
    missing_tools: set[str] = field(default_factory=set)
    unexpected_tools: set[str] = field(default_factory=set)


def _side_contacts(frame: PerceptionFrame) -> dict[str, str]:
    """side -> object_label, for hands that are actually touching something.
    Side-preserving (unlike a flat label set) so wrong_hand_state can tell
    "right hand touching the rib tool" apart from "left hand touching the
    rib tool" even though both put "rib_tool" in the contact set."""
    return {c.side: c.object_label for c in frame.contacts if c.object_label is not None}


def _hand_state_labels(step: StepTemplate) -> set[str]:
    labels: set[str] = set()
    for side_targets in step.hand_state.values():
        labels.update(side_targets)
    return labels


class Comparator:
    def __init__(self, templates: CraftTemplates):
        self.templates = templates

    def compare(self, frame: PerceptionFrame, active_step: StepTemplate) -> ComparisonResult:
        side_contacts = _side_contacts(frame)
        contact_labels = set(side_contacts.values())
        if not contact_labels:
            return ComparisonResult(state=ComparisonState.NO_EVIDENCE, detail="No hand-object contact detected this frame.")

        required_tools = set(active_step.required_tools)
        expected = required_tools | _hand_state_labels(active_step)
        matched = contact_labels & expected
        unexpected = contact_labels - expected

        if not matched:
            other_step = self._best_other_step_match(frame, active_step)
            if other_step is not None:
                return ComparisonResult(
                    state=ComparisonState.WRONG_SEQUENCE,
                    detail=(
                        f"Contact matches step {other_step.step_index} "
                        f"({other_step.narration[:60]!r}) better than the active step "
                        f"{active_step.step_index}."
                    ),
                    unexpected_tools=unexpected,
                    missing_tools=required_tools,
                )
            return ComparisonResult(
                state=ComparisonState.WRONG_TOOL,
                detail=f"Contact with {sorted(contact_labels)} does not match this step's required tools {sorted(required_tools)}.",
                missing_tools=required_tools,
                unexpected_tools=unexpected,
            )

        if required_tools and not (contact_labels & required_tools):
            return ComparisonResult(
                state=ComparisonState.WRONG_TOOL,
                detail=f"Missing required tool contact: {sorted(required_tools)}.",
                matched_tools=matched,
                missing_tools=required_tools - contact_labels,
                unexpected_tools=unexpected,
            )

        # Right tool is being touched by *some* hand — now check *which*
        # hand, per side, against hand_state. This is where "holding the
        # right tool with the wrong hand" gets caught.
        wrong_side_targets: set[str] = set()
        for side, targets in active_step.hand_state.items():
            if side_contacts.get(side) not in targets:
                wrong_side_targets.update(targets)
        if wrong_side_targets:
            return ComparisonResult(
                state=ComparisonState.WRONG_HAND_STATE,
                detail=f"Tool contact is present, but not the expected hand placement {sorted(active_step.hand_state.items())}.",
                matched_tools=matched,
                missing_tools=wrong_side_targets,
                unexpected_tools=unexpected,
            )

        if required_tools.issubset(contact_labels):
            return ComparisonResult(
                state=ComparisonState.STEP_COMPLETE,
                detail="All expected tool/hand contacts observed for this step.",
                matched_tools=matched,
            )

        return ComparisonResult(state=ComparisonState.ON_TRACK, detail="Contact matches the active step.", matched_tools=matched)

    def _best_other_step_match(self, frame: PerceptionFrame, active_step: StepTemplate) -> StepTemplate | None:
        contact_labels = set(_side_contacts(frame).values())
        best_step, best_score = None, 0
        for step in self.templates.steps:
            if step.step_index == active_step.step_index:
                continue
            expected = set(step.required_tools) | _hand_state_labels(step)
            score = len(contact_labels & expected)
            if score > best_score:
                best_step, best_score = step, score
        return best_step
