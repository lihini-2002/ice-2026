"""State machine that tracks which step of a craft the learner is likely
attempting, given a stream of PerceptionFrame contact events.

There's no continuous hand-pose/trajectory data on the learner side — only
discrete hand-touching-object contact events — so step detection is built
around contact-state matching rather than motion-trajectory matching, and
uses a sliding-window vote to smooth out single-frame noise, echoing the
offline pipeline's frequency-ranking philosophy (scripts/fuse_steps.py ranks
tools/gaze/hand targets by how often they're observed within a step, rather
than trusting any single sample).
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass

from .perception import PerceptionFrame
from .step_templates import CraftTemplates, StepTemplate

DEFAULT_WINDOW_SIZE = 15  # frames


def _contact_labels(frame: PerceptionFrame) -> set[str]:
    return {c.object_label for c in frame.contacts if c.object_label is not None}


def score_step(frame: PerceptionFrame, step: StepTemplate) -> int:
    """How well this frame's contact state matches a step template: a count
    of required_tools/hand_state labels currently in contact. Simple overlap
    counting, not a learned model — keeps the tracker debuggable against real
    footage, same rule-based philosophy as comparator.py."""
    labels = _contact_labels(frame)
    score = sum(1 for tool in step.required_tools if tool in labels)
    for side_targets in step.hand_state.values():
        score += sum(1 for tool in side_targets if tool in labels)
    return score


@dataclass
class StepTrackerResult:
    active_step_index: int
    votes: Counter


class StepTracker:
    """Sliding-window plurality vote over which step's contact signature best
    matches each incoming frame. Ties (including "no evidence this frame")
    favor staying on the currently active step, so a single ambiguous or
    empty frame doesn't cause flapping."""

    def __init__(self, templates: CraftTemplates, window_size: int = DEFAULT_WINDOW_SIZE):
        if not templates.steps:
            raise ValueError("CraftTemplates has no steps to track")
        self.templates = templates
        self.window_size = window_size
        self._window: deque[int | None] = deque(maxlen=window_size)
        self._active_step_index: int = templates.steps[0].step_index

    @property
    def active_step(self) -> StepTemplate:
        return next(s for s in self.templates.steps if s.step_index == self._active_step_index)

    def _best_matching_step(self, frame: PerceptionFrame) -> int | None:
        scores = {s.step_index: score_step(frame, s) for s in self.templates.steps}
        best_score = max(scores.values())
        if best_score == 0:
            return None  # no contact evidence this frame — abstain from voting
        candidates = [idx for idx, sc in scores.items() if sc == best_score]
        if self._active_step_index in candidates:
            return self._active_step_index
        return min(candidates)

    def update(self, frame: PerceptionFrame) -> StepTrackerResult:
        self._window.append(self._best_matching_step(frame))
        votes = Counter(v for v in self._window if v is not None)
        if votes:
            top_count = max(votes.values())
            leaders = [idx for idx, c in votes.items() if c == top_count]
            if self._active_step_index not in leaders:
                self._active_step_index = min(leaders)
        return StepTrackerResult(active_step_index=self._active_step_index, votes=votes)

    def advance_to_next_step(self) -> StepTemplate | None:
        """Explicitly move to the next step in sequence (e.g. called by an
        orchestrator after comparator.py reports STEP_COMPLETE for a few
        consecutive frames). Returns None and leaves state unchanged if
        already on the last step. Clears the vote window so the new step
        isn't immediately overridden by stale votes for the old one."""
        indices = sorted(s.step_index for s in self.templates.steps)
        pos = indices.index(self._active_step_index)
        if pos + 1 >= len(indices):
            return None
        self._active_step_index = indices[pos + 1]
        self._window.clear()
        return self.active_step
