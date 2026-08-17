"""Unit tests for command_generator.py: debouncing and the unreviewed/empty
command_templates fallback."""

from __future__ import annotations

import unittest

from learning_runtime.comparator import ComparisonResult, ComparisonState
from learning_runtime.command_generator import CommandGenerator
from learning_runtime.step_templates import StepTemplate


class _FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestCommandGenerator(unittest.TestCase):
    def test_debounces_repeated_correction_within_window(self):
        step = StepTemplate(
            step_index=0,
            narration="Center the clay.",
            required_tools=["clay"],
            command_templates={"correct_tool": ["Pick up the clay."]},
            command_templates_reviewed=True,
        )
        clock = _FakeClock()
        generator = CommandGenerator(debounce_seconds=8.0, clock=clock)
        comparison = ComparisonResult(state=ComparisonState.WRONG_TOOL, detail="")

        first = generator.generate(comparison, step)
        self.assertIsNotNone(first)
        self.assertEqual(first.text, "Pick up the clay.")

        clock.advance(2.0)  # still within the debounce window
        self.assertIsNone(generator.generate(comparison, step))

        clock.advance(7.0)  # now past 8s total
        second = generator.generate(comparison, step)
        self.assertIsNotNone(second)

    def test_falls_back_to_generic_sentence_when_unreviewed(self):
        step = StepTemplate(
            step_index=0,
            narration="Center the clay on the wheel.",
            required_tools=["clay"],
            command_templates={"correct_tool": ["This text should never be used."]},
            command_templates_reviewed=False,  # unreviewed — must not be delivered
        )
        generator = CommandGenerator()
        comparison = ComparisonResult(state=ComparisonState.WRONG_TOOL, detail="")

        command = generator.generate(comparison, step)

        self.assertIsNotNone(command)
        self.assertIn("Center the clay on the wheel.", command.text)
        self.assertNotIn("This text should never be used.", command.text)

    def test_no_evidence_produces_no_command(self):
        step = StepTemplate(step_index=0, narration="Center the clay.")
        generator = CommandGenerator()
        comparison = ComparisonResult(state=ComparisonState.NO_EVIDENCE, detail="")

        self.assertIsNone(generator.generate(comparison, step))


if __name__ == "__main__":
    unittest.main()
