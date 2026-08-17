"""Shared types and paths for the pilot pipeline.

The pipeline works off a session split across two top-level directories,
keyed by the same session_id:

    videos/<session_id>/          # input — supplied before running the pipeline
        meta.json                 # artisan, craft, task, date — written by hand per docs/capture_protocol.md
        raw/<name>.vrs             # exported Aria recording
        mps/                       # MPS eye-gaze + hand-tracking outputs (from the MPS cloud request)

    outputs/<session_id>/         # output — written by the pipeline stages
        derived/
            transcript.json        # written by transcribe.py
            objects.json           # written by extract_scene_objects.py
            gaze_hand_targets.json # written by extract_gaze_hand_targets.py
            frames/                # sampled RGB frames referenced by objects.json / session.json
        session.json                # written by fuse_steps.py — the knowledge-base unit
        session.md                  # human-readable rendering of session.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VIDEOS_ROOT = REPO_ROOT / "videos"
DEFAULT_OUTPUTS_ROOT = REPO_ROOT / "outputs"


@dataclass
class SessionPaths:
    session_id: str
    videos_root: Path = DEFAULT_VIDEOS_ROOT
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT

    @property
    def input_dir(self) -> Path:
        return self.videos_root / self.session_id

    @property
    def output_dir(self) -> Path:
        return self.outputs_root / self.session_id

    # Kept as `root` (rather than renaming every call site) since it's used
    # as the base for frame paths stored relative in objects.json — those
    # live under output_dir, so this stays output_dir.
    @property
    def root(self) -> Path:
        return self.output_dir

    @property
    def meta(self) -> Path:
        return self.input_dir / "meta.json"

    @property
    def raw_dir(self) -> Path:
        return self.input_dir / "raw"

    @property
    def mps_dir(self) -> Path:
        return self.input_dir / "mps"

    @property
    def derived_dir(self) -> Path:
        return self.output_dir / "derived"

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
    def gaze_hand_json(self) -> Path:
        return self.derived_dir / "gaze_hand_targets.json"

    @property
    def session_json(self) -> Path:
        return self.output_dir / "session.json"

    @property
    def session_md(self) -> Path:
        return self.output_dir / "session.md"

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
    gaze_targets: list[str] = field(default_factory=list)
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
