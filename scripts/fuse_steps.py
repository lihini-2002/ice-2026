"""Stage 4: fuse transcript + detected objects + hand-tracking into the
per-step knowledge-base entries, and write session.json / session.md.

Step boundaries come from the narration cue phrases artisans are asked to
use (see docs/capture_protocol.md): a transcript segment starting with
"next, i" / "now i'm going to" (etc.) starts a new step.

Hand-object association (e.g. "gripping the chisel") needs projecting 3D
hand landmarks into the RGB camera frame via device calibration, which is
out of scope for this pilot — instead we report per-step hand-tracking
coverage (which hand(s) were tracked, how continuously) as a starting
signal, and leave precise hand↔tool linking as future work.

Usage:
    python scripts/fuse_steps.py output/<session_id>
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import SessionPaths, Session, Step, load_json, write_json

STEP_CUE_RE = re.compile(r"^\s*(next,?\s+i|now\s+i'?m\s+going\s+to|now\s+i\s+will)\b", re.IGNORECASE)
IGNORED_OBJECT_LABELS = {"hand", "table", "workbench"}
OBJECT_SCORE_MIN = 0.2


def segment_into_steps(transcript: list[dict]) -> list[Step]:
    if not transcript:
        return []

    steps: list[Step] = []
    current = None
    for seg in transcript:
        starts_new_step = STEP_CUE_RE.match(seg["text"]) is not None
        if current is None or starts_new_step:
            if current is not None:
                steps.append(current)
            current = Step(start_s=seg["start_s"], end_s=seg["end_s"], narration=seg["text"])
        else:
            current.end_s = seg["end_s"]
            current.narration += " " + seg["text"]
    if current is not None:
        steps.append(current)
    return steps


def attach_objects(steps: list[Step], objects: list[dict]) -> None:
    for step in steps:
        counts: Counter[str] = Counter()
        frames_in_step = []
        for frame in objects:
            if not (step.start_s <= frame["timestamp_s"] <= step.end_s):
                continue
            frames_in_step.append(frame["frame"])
            for obj in frame["objects"]:
                if obj["label"] in IGNORED_OBJECT_LABELS or obj["score"] < OBJECT_SCORE_MIN:
                    continue
                counts[obj["label"]] += 1
        step.tools_used = [label for label, _ in counts.most_common()]
        step.frame_refs = frames_in_step[:2]  # a couple of representative frames


def attach_hand_tracking(steps: list[Step], mps_dir: Path) -> None:
    hand_files = list(mps_dir.glob("**/hand_tracking_results.csv"))
    if not hand_files:
        for step in steps:
            step.hand_actions = ["no hand-tracking data available"]
        return

    from projectaria_tools.core.mps.hand_tracking import read_hand_tracking_results

    results = read_hand_tracking_results(str(hand_files[0]))
    by_step: dict[int, dict[str, int]] = defaultdict(lambda: {"left": 0, "right": 0})

    for r in results:
        t_s = r.tracking_timestamp.total_seconds()
        for i, step in enumerate(steps):
            if step.start_s <= t_s <= step.end_s:
                if r.left_hand is not None:
                    by_step[i]["left"] += 1
                if r.right_hand is not None:
                    by_step[i]["right"] += 1
                break

    for i, step in enumerate(steps):
        counts = by_step.get(i, {"left": 0, "right": 0})
        actions = []
        if counts["left"]:
            actions.append(f"left hand tracked ({counts['left']} samples)")
        if counts["right"]:
            actions.append(f"right hand tracked ({counts['right']} samples)")
        step.hand_actions = actions or ["no hand-tracking data in this step"]


def render_markdown(session: Session) -> str:
    lines = [
        f"# {session.craft} — {session.task_description}",
        f"Artisan: {session.artisan_id}  |  Date: {session.date}  |  Session: {session.session_id}",
        "",
    ]
    for i, step in enumerate(session.steps, 1):
        lines.append(f"## Step {i} ({step.start_s:.1f}s–{step.end_s:.1f}s)")
        lines.append(step.narration)
        if step.tools_used:
            lines.append(f"- **Tools/materials seen:** {', '.join(step.tools_used)}")
        if step.hand_actions:
            lines.append(f"- **Hands:** {', '.join(step.hand_actions)}")
        if step.frame_refs:
            lines.append(f"- **Frames:** {', '.join(step.frame_refs)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()

    paths = SessionPaths(args.session_dir)
    meta = load_json(paths.meta)
    transcript = load_json(paths.transcript_json)
    objects = load_json(paths.objects_json) if paths.objects_json.exists() else []

    steps = segment_into_steps(transcript)
    attach_objects(steps, objects)
    attach_hand_tracking(steps, paths.mps_dir)

    session = Session(
        session_id=paths.root.name,
        craft=meta["craft"],
        artisan_id=meta["artisan_id"],
        date=meta["date"],
        task_description=meta["task_description"],
        steps=steps,
    )

    write_json(paths.session_json, session)
    paths.session_md.write_text(render_markdown(session))
    print(f"Wrote {len(steps)} steps to {paths.session_json} and {paths.session_md}")


if __name__ == "__main__":
    main()
