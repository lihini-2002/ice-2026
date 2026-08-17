"""Unit tests for comparator.py using synthetic step_templates + synthetic
perception-output sequences — covers at least one "wrong tool," one "wrong
sequence," and one "on track" case, as required for the comparator's
rule-based classification to be trustworthy against real footage."""

from __future__ import annotations

import unittest

from learning_runtime.comparator import Comparator, ComparisonState
from learning_runtime.step_templates import CraftTemplates, StepTemplate

from .synthetic import make_frame, two_step_templates


class TestComparator(unittest.TestCase):
    def test_on_track_when_partial_contact_matches_active_step(self):
        # A step with two required tools, only one of which is in contact —
        # genuinely "on track" (not complete, not wrong).
        step = StepTemplate(step_index=0, narration="Wet the clay and center it.", required_tools=["clay", "water_bowl"])
        templates = CraftTemplates.from_steps([step])
        comparator = Comparator(templates)

        frame = make_frame(0.0, right="clay")
        result = comparator.compare(frame, step)

        self.assertEqual(result.state, ComparisonState.ON_TRACK)
        self.assertIn("clay", result.matched_tools)

    def test_wrong_tool_when_contact_matches_no_step(self):
        templates = two_step_templates()
        active_step = templates.steps[0]  # requires "clay"
        comparator = Comparator(templates)

        frame = make_frame(0.0, right="sponge")  # not required by any step
        result = comparator.compare(frame, active_step)

        self.assertEqual(result.state, ComparisonState.WRONG_TOOL)
        self.assertIn("clay", result.missing_tools)

    def test_wrong_sequence_when_contact_matches_a_different_step(self):
        templates = two_step_templates()
        active_step = templates.steps[0]  # requires "clay"
        comparator = Comparator(templates)

        # Learner is touching step 1's tool while step 0 is still active.
        frame = make_frame(0.0, right="rib_tool")
        result = comparator.compare(frame, active_step)

        self.assertEqual(result.state, ComparisonState.WRONG_SEQUENCE)
        self.assertIn("step 1", result.detail)

    def test_step_complete_when_all_expected_contacts_present(self):
        templates = two_step_templates()
        active_step = templates.steps[0]  # required_tools=["clay"], hand_state={"right": ["clay"]}
        comparator = Comparator(templates)

        frame = make_frame(0.0, right="clay")
        result = comparator.compare(frame, active_step)

        self.assertEqual(result.state, ComparisonState.STEP_COMPLETE)

    def test_wrong_hand_state_when_tool_contact_present_but_wrong_hand(self):
        step = StepTemplate(step_index=0, narration="Grip the rib tool with your left hand.", required_tools=["rib_tool"], hand_state={"left": ["rib_tool"]})
        templates = CraftTemplates.from_steps([step])
        comparator = Comparator(templates)

        # rib_tool is in contact (satisfies required_tools) but via the right
        # hand, not the left hand the step calls for.
        frame = make_frame(0.0, right="rib_tool")
        result = comparator.compare(frame, step)

        self.assertEqual(result.state, ComparisonState.WRONG_HAND_STATE)

    def test_no_evidence_when_no_contact_detected(self):
        templates = two_step_templates()
        comparator = Comparator(templates)

        frame = make_frame(0.0, right=None)
        result = comparator.compare(frame, templates.steps[0])

        self.assertEqual(result.state, ComparisonState.NO_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
