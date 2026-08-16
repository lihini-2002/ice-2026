"""Shared types and paths for the pilot pipeline.

The pipeline works entirely off a session directory laid out as:

    output/<session_id>/
        meta.json                 # artisan, craft, task, date — written by hand per docs/capture_protocol.md
        raw/<name>.vrs             # exported Aria recording
        mps/                       # MPS eye-gaze + hand-tracking outputs (from the MPS cloud request)
        derived/
            transcript.json        # written by transcribe.py
            objects.json           # written by extract_scene_objects.py
            frames/                # sampled RGB frames referenced by objects.json / session.json
        session.json                # written by fuse_steps.py — the knowledge-base unit
        session.md                  # human-readable rendering of session.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SessionPaths:
    root: Path

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def mps_dir(self) -> Path:
        return self.root / "mps"

    @property
    def derived_dir(self) -> Path:
        return self.root / "derived"

    @property
    def frames_dir(self) -> Path:
        return self.derived_dir / "frames"

    @property
    def transcript_json(self) -> Path:
        return self.derived_dir / "transcript.json"

    @property
    def objects_json(self) -> Path:
        return self.derived_dir / "objects.json"

    @property
    def session_json(self) -> Path:
        return self.root / "session.json"

    @property
    def session_md(self) -> Path:
        return self.root / "session.md"

    def vrs_file(self) -> Path:
        candidates = sorted(self.raw_dir.glob("*.vrs"))
        if not candidates:
            raise FileNotFoundError(f"No .vrs file found in {self.raw_dir}")
        if len(candidates) > 1:
            raise ValueError(f"Expected exactly one .vrs file in {self.raw_dir}, found {len(candidates)}")
        return candidates[0]

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.mps_dir, self.derived_dir, self.frames_dir):
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class TranscriptSegment:
    start_s: float
    end_s: float
    text: str


@dataclass
class Step:
    start_s: float
    end_s: float
    narration: str
    tools_used: list[str] = field(default_factory=list)
    hand_actions: list[str] = field(default_factory=list)
    frame_refs: list[str] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    craft: str
    artisan_id: str
    date: str
    task_description: str
    steps: list[Step] = field(default_factory=list)


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=asdict)
