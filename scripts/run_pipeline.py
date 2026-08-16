"""Orchestrates the full pilot pipeline: ingest -> transcribe -> detect objects
-> fuse into session.json / session.md.

Usage:
    python scripts/run_pipeline.py output/<session_id>

Expects, before running:
    output/<session_id>/meta.json      (see meta.example.json)
    output/<session_id>/raw/*.vrs      (the exported recording)
    output/<session_id>/mps/           (optional — MPS hand-tracking/eye-gaze results)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

STAGES = ["ingest_vrs.py", "transcribe.py", "extract_scene_objects.py", "fuse_steps.py"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--skip", nargs="*", default=[], help="stage filenames to skip, e.g. --skip extract_scene_objects.py")
    args = parser.parse_args()

    session_dir = args.session_dir.resolve()
    if not (session_dir / "meta.json").exists():
        sys.exit(f"Missing {session_dir / 'meta.json'} — see docs/capture_protocol.md and meta.example.json")

    scripts_dir = Path(__file__).parent
    for stage in STAGES:
        if stage in args.skip:
            print(f"-- skipping {stage} --")
            continue
        print(f"\n== running {stage} ==")
        subprocess.run([sys.executable, str(scripts_dir / stage), str(session_dir)], check=True)

    print(f"\nDone. Knowledge-base entry at {session_dir / 'session.json'}")


if __name__ == "__main__":
    main()
