"""Offline validation entry point: run the full learning_runtime loop
(perception -> step_tracker -> comparator -> command_generator -> delivery)
against a pre-recorded learner video file. This is the first thing to run
and inspect before any live-camera integration is attempted.

A step is advanced automatically once the comparator reports STEP_COMPLETE
for CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE consecutive sampled frames — a
simple debounce so one lucky frame of overlapping contact doesn't skip a
step.

Usage:
    python -m learning_runtime.run_offline_test <video_path> <step_templates_json>

By default this uses StubObjectDetector, which raises as soon as detection
is actually requested — pass a real ObjectDetector (see perception.py) via
the `detector` argument to run() when calling this as a library rather than
a CLI, e.g. from a notebook wiring in a distilled OWLv2 checkpoint.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .comparator import Comparator, ComparisonState
from .command_generator import CommandGenerator
from .delivery import DeliveryChannel, PrintDeliveryChannel, VisualOverlay
from .perception import ObjectDetector, Perception, StubObjectDetector
from .step_templates import CraftTemplates
from .step_tracker import StepTracker

CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE = 5


def _step_vocabulary(templates: CraftTemplates) -> list[str]:
    vocabulary: set[str] = set()
    for step in templates.steps:
        vocabulary.update(step.required_tools)
        for side_targets in step.hand_state.values():
            vocabulary.update(side_targets)
    return sorted(vocabulary)


def run(
    video_path: Path,
    step_templates_path: Path,
    detector: ObjectDetector | None = None,
    delivery: DeliveryChannel | None = None,
    sample_every_n_frames: int = 5,
) -> None:
    import cv2  # deferred: only this entry point needs it, not the unit-testable core

    templates = CraftTemplates.load(step_templates_path)
    perception = Perception(detector=detector or StubObjectDetector(), vocabulary=_step_vocabulary(templates))
    tracker = StepTracker(templates)
    comparator = Comparator(templates)
    commander = CommandGenerator()
    delivery = delivery or PrintDeliveryChannel()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    consecutive_complete = 0
    frame_idx = 0
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            if frame_idx % sample_every_n_frames != 0:
                frame_idx += 1
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            timestamp_s = frame_idx / fps

            perception_frame = perception.process_frame(frame_rgb, timestamp_s)
            tracker.update(perception_frame)
            active_step = tracker.active_step
            comparison = comparator.compare(perception_frame, active_step)

            delivery.show_overlay(VisualOverlay(
                step_index=active_step.step_index,
                total_steps=len(templates.steps),
                caption=f"t={timestamp_s:.1f}s {comparison.state.value}",
                highlighted_boxes=[obj.box for obj in perception_frame.objects],
            ))
            command = commander.generate(comparison, active_step)
            if command is not None:
                delivery.speak(command)

            if comparison.state == ComparisonState.STEP_COMPLETE:
                consecutive_complete += 1
                if consecutive_complete >= CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE:
                    if tracker.advance_to_next_step() is not None:
                        print(f"-- advanced to step {tracker.active_step.step_index} --")
                    consecutive_complete = 0
            else:
                consecutive_complete = 0

            frame_idx += 1
    finally:
        cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video_path", type=Path)
    parser.add_argument("step_templates_json", type=Path)
    parser.add_argument("--sample-every-n-frames", type=int, default=5, help="perception runs every Nth frame (default 5)")
    args = parser.parse_args()
    run(args.video_path, args.step_templates_json, sample_every_n_frames=args.sample_every_n_frames)


if __name__ == "__main__":
    main()
