"""Stage 5: fuse transcript + detected objects + gaze/hand targets into the
per-step knowledge-base entries, and write session.json / session.md.

Step boundaries come from the narration cue phrases artisans are asked to
use (see docs/capture_protocol.md): a transcript segment starting with
"next, i" / "now i'm going to" (etc.) starts a new step.

Hand-object and gaze-object association ("gripping the rib tool", "looking
at the clay") comes from extract_gaze_hand_targets.py's per-sample
projection of MPS gaze/hand data onto the detected-object boxes; this stage
just aggregates those samples per step into a ranked, human-readable
summary.

Usage:
    python scripts/fuse_steps.py output/<session_id>
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

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


def _ranked_targets(counts: Counter[str], total: int, top_n: int = 2) -> list[str]:
    if total == 0:
        return []
    return [f"{label} ({100 * n // total}%)" for label, n in counts.most_common(top_n)]


def attach_gaze_and_hand_targets(steps: list[Step], samples: list[dict]) -> None:
    if not samples:
        for step in steps:
            step.gaze_targets = ["no eye-gaze data available"]
            step.hand_actions = ["no hand-tracking data available"]
        return

    for step in steps:
        in_step = [s for s in samples if step.start_s <= s["timestamp_s"] <= step.end_s]

        gaze_counts: Counter[str] = Counter(s["gaze_target"] for s in in_step if s.get("gaze_target"))
        gaze_total = sum(1 for s in in_step if "gaze_target" in s)
        step.gaze_targets = _ranked_targets(gaze_counts, gaze_total) or (
            ["no eye-gaze data in this step"] if gaze_total == 0 else ["gaze not on a detected object"]
        )

        actions = []
        for side in ("left", "right"):
            key = f"{side}_hand_target"
            side_counts: Counter[str] = Counter(s[key] for s in in_step if s.get(key))
            side_total = sum(1 for s in in_step if key in s)
            if side_total == 0:
                continue
            ranked = _ranked_targets(side_counts, side_total)
            if ranked:
                actions.append(f"{side} hand on {ranked[0]}")
            else:
                actions.append(f"{side} hand tracked, not on a detected object ({side_total} samples)")
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
        if step.gaze_targets:
            lines.append(f"- **Looking at:** {', '.join(step.gaze_targets)}")
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
    gaze_hand_samples = load_json(paths.gaze_hand_json) if paths.gaze_hand_json.exists() else []

    steps = segment_into_steps(transcript)
    attach_objects(steps, objects)
    attach_gaze_and_hand_targets(steps, gaze_hand_samples)

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
