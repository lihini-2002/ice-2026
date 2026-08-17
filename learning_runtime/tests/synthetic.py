"""Synthetic fixtures shared by the learning_runtime tests: a two-step craft
template and a helper for building PerceptionFrame contact events without
running real perception."""

from __future__ import annotations

from learning_runtime.perception import HandContact, PerceptionFrame
from learning_runtime.step_templates import CraftTemplates, StepTemplate

STEP_CENTER = StepTemplate(
    step_index=0,
    narration="Next, I center the clay on the wheel.",
    required_tools=["clay"],
    hand_state={"right": ["clay"]},
    gaze_focus="clay",
)

STEP_OPEN = StepTemplate(
    step_index=1,
    narration="Now I'm going to open the clay with the rib tool.",
    required_tools=["rib_tool"],
    hand_state={"right": ["rib_tool"]},
    gaze_focus="clay",
)


def two_step_templates() -> CraftTemplates:
    return CraftTemplates.from_steps([STEP_CENTER, STEP_OPEN], craft="pottery", task_description="Throw a small bowl")


def make_frame(timestamp_s: float, **side_to_label: str | None) -> PerceptionFrame:
    """make_frame(1.0, right="clay", left=None) -> a frame whose right hand is
    in contact with "clay" and whose left hand is tracked but touching
    nothing."""
    contacts = [HandContact(side=side, object_label=label, distance=0.01 if label else 1.0) for side, label in side_to_label.items()]
    return PerceptionFrame(timestamp_s=timestamp_s, objects=[], hands=[], contacts=contacts)
