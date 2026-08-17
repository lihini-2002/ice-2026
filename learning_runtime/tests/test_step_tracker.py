"""Unit tests for step_tracker.py using synthetic step_templates + synthetic
perception-output sequences."""

from __future__ import annotations

import unittest

from learning_runtime.step_tracker import StepTracker, score_step

from .synthetic import make_frame, two_step_templates


class TestScoreStep(unittest.TestCase):
    def test_score_counts_required_tool_and_hand_state_matches(self):
        templates = two_step_templates()
        frame = make_frame(0.0, right="clay")
        self.assertEqual(score_step(frame, templates.steps[0]), 2)  # clay in required_tools AND hand_state
        self.assertEqual(score_step(frame, templates.steps[1]), 0)

    def test_score_zero_with_no_contact(self):
        templates = two_step_templates()
        frame = make_frame(0.0, right=None)
        self.assertEqual(score_step(frame, templates.steps[0]), 0)


class TestStepTracker(unittest.TestCase):
    def test_on_track_stays_on_initial_step(self):
        tracker = StepTracker(two_step_templates(), window_size=5)
        for t in range(10):
            result = tracker.update(make_frame(float(t), right="clay"))
        self.assertEqual(result.active_step_index, 0)
        self.assertEqual(tracker.active_step.step_index, 0)

    def test_sustained_contact_with_next_step_tool_shifts_active_step(self):
        tracker = StepTracker(two_step_templates(), window_size=5)
        # A few frames of ambiguous/no contact shouldn't be enough to move.
        for t in range(3):
            tracker.update(make_frame(float(t), right=None))
        self.assertEqual(tracker.active_step.step_index, 0)

        # Sustained contact with step 1's tool should win the sliding-window vote.
        result = None
        for t in range(3, 20):
            result = tracker.update(make_frame(float(t), right="rib_tool"))
        self.assertEqual(result.active_step_index, 1)
        self.assertEqual(tracker.active_step.step_index, 1)

    def test_single_ambiguous_frame_does_not_flip_active_step(self):
        tracker = StepTracker(two_step_templates(), window_size=5)
        for t in range(5):
            tracker.update(make_frame(float(t), right="clay"))
        self.assertEqual(tracker.active_step.step_index, 0)

        # One frame touching the other step's tool, surrounded by clay contact,
        # shouldn't be enough to move off the plurality-held step.
        tracker.update(make_frame(5.0, right="rib_tool"))
        result = tracker.update(make_frame(6.0, right="clay"))
        self.assertEqual(result.active_step_index, 0)

    def test_advance_to_next_step_moves_forward_and_clears_window(self):
        tracker = StepTracker(two_step_templates(), window_size=5)
        for t in range(5):
            tracker.update(make_frame(float(t), right="clay"))
        self.assertEqual(tracker.active_step.step_index, 0)

        next_step = tracker.advance_to_next_step()
        self.assertIsNotNone(next_step)
        self.assertEqual(next_step.step_index, 1)
        self.assertEqual(tracker.active_step.step_index, 1)

    def test_advance_to_next_step_returns_none_at_last_step(self):
        tracker = StepTracker(two_step_templates(), window_size=5)
        tracker.advance_to_next_step()  # move to step 1 (the last step)
        self.assertIsNone(tracker.advance_to_next_step())
        self.assertEqual(tracker.active_step.step_index, 1)


if __name__ == "__main__":
    unittest.main()
