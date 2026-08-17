"""Output delivery interface: audio (TTS) coaching + visual (bounding-box /
progress) overlay. Actual TTS and mobile rendering will be wired in by the
mobile app — this ships a clean interface plus a print-based mock so the
rest of the runtime can be exercised end-to-end today (see
run_offline_test.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .command_generator import Command
from .perception import BoundingBox


@dataclass
class VisualOverlay:
    step_index: int
    total_steps: int
    caption: str
    highlighted_boxes: list[BoundingBox] = field(default_factory=list)


class DeliveryChannel(Protocol):
    def speak(self, command: Command) -> None: ...
    def show_overlay(self, overlay: VisualOverlay) -> None: ...


class PrintDeliveryChannel:
    """Mock/print-based implementation for offline validation. Replace with
    a real TTS + mobile-rendering implementation of DeliveryChannel later —
    nothing else in learning_runtime needs to change."""

    def speak(self, command: Command) -> None:
        print(f"[audio:{command.category}] {command.text}")

    def show_overlay(self, overlay: VisualOverlay) -> None:
        boxes = ", ".join(f"({b.x0:.2f},{b.y0:.2f})-({b.x1:.2f},{b.y1:.2f})" for b in overlay.highlighted_boxes)
        print(f"[overlay] step {overlay.step_index + 1}/{overlay.total_steps} [{overlay.caption}] boxes=[{boxes}]")
