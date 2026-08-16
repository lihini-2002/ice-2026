"""Orchestrates the full pilot pipeline: ingest -> transcribe -> detect objects
-> fuse into session.json / session.md.

Usage:
    python scripts/run_pipeline.py <session_id>

Expects, before running:
    videos/<session_id>/meta.json      (see meta.example.json)
    videos/<session_id>/raw/*.vrs      (the exported recording)
    videos/<session_id>/mps/           (optional — MPS hand-tracking/eye-gaze results)

Writes results to outputs/<session_id>/.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import SessionPaths

STAGES = [
    "ingest_vrs.py",
    "transcribe.py",
    "extract_scene_objects.py",
    "extract_gaze_hand_targets.py",
    "fuse_steps.py",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--skip", nargs="*", default=[], help="stage filenames to skip, e.g. --skip extract_scene_objects.py")
    args = parser.parse_args()

    paths = SessionPaths(args.session_id)
    if not paths.meta.exists():
        sys.exit(f"Missing {paths.meta} — see docs/capture_protocol.md and meta.example.json")

    scripts_dir = Path(__file__).parent
    for stage in STAGES:
        if stage in args.skip:
            print(f"-- skipping {stage} --")
            continue
        print(f"\n== running {stage} ==")
        subprocess.run([sys.executable, str(scripts_dir / stage), args.session_id], check=True)

    print(f"\nDone. Knowledge-base entry at {paths.session_json}")


if __name__ == "__main__":
    main()
