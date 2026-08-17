"""Stage 5b (authoring): fuse a mistake_demo session's transcript into an
*existing* step_templates.json's common_mistakes fields, instead of creating
steps from scratch the way fuse_steps.py does for a primary session.

See docs/mistake_elicitation_protocol.md for the recording protocol and the
"For step N, a common mistake is... / The correction is..." narration cue
this script parses.

Usage:
    python scripts/fuse_mistake_demo.py output/<mistake_session_id> \\
        --step-templates output/<primary_session_id>/step_templates.json
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import SessionPaths, load_json, write_json

# "For step 2, a common mistake is..." / "For step 2 a common mistake is..."
# — case-insensitive, tolerant of the artisan's exact phrasing around the cue.
STEP_TAG_RE = re.compile(r"for\s+step\s+(\d+)\b", re.IGNORECASE)
CORRECTION_CUE_RE = re.compile(r"\bthe\s+correction\s+is\b\s*:?\s*", re.IGNORECASE)


def segment_into_mistake_blocks(transcript: list[dict]) -> list[dict]:
    """Group transcript segments into per-step-number mistake blocks using
    the "For step N, a common mistake is..." cue — mirrors fuse_steps.py's
    segment_into_steps, but keyed by an explicit step number instead of
    sequential order, since a mistake-demo session doesn't recreate every
    step of the primary session."""
    blocks: list[dict] = []
    current: dict | None = None
    for seg in transcript:
        m = STEP_TAG_RE.search(seg["text"])
        if m:
            if current is not None:
                blocks.append(current)
            current = {"step_index": int(m.group(1)) - 1, "start_s": seg["start_s"], "end_s": seg["end_s"], "text": seg["text"]}
        elif current is not None:
            current["end_s"] = seg["end_s"]
            current["text"] += " " + seg["text"]
    if current is not None:
        blocks.append(current)
    return blocks


def split_mistake_and_correction(text: str) -> tuple[str, str | None]:
    parts = CORRECTION_CUE_RE.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), None


def frame_ref_for_block(block: dict, objects: list[dict]) -> str | None:
    for frame in objects:
        if block["start_s"] <= frame["timestamp_s"] <= block["end_s"]:
            return frame["frame"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mistake_session_dir", type=Path, help="output/<mistake_demo_session_id>")
    parser.add_argument(
        "--step-templates",
        type=Path,
        help="path to the primary session's step_templates.json (defaults to meta.json's linked_step_template_session)",
    )
    args = parser.parse_args()

    paths = SessionPaths(args.mistake_session_dir)
    meta = load_json(paths.meta)
    if meta.get("session_type") != "mistake_demo":
        raise ValueError(f"{paths.meta} is not a mistake_demo session (session_type={meta.get('session_type')!r})")

    step_templates_path = args.step_templates
    if step_templates_path is None:
        linked = meta.get("linked_step_template_session")
        if not linked:
            raise ValueError(
                "No --step-templates given and meta.json has no linked_step_template_session — "
                "see docs/mistake_elicitation_protocol.md"
            )
        step_templates_path = paths.root.parent / linked / "step_templates.json"

    if not step_templates_path.exists():
        raise FileNotFoundError(f"{step_templates_path} not found — run generate_step_templates.py on the primary session first.")
    template_set = load_json(step_templates_path)
    steps_by_index = {s["step_index"]: s for s in template_set["steps"]}

    transcript = load_json(paths.transcript_json)
    objects = load_json(paths.objects_json) if paths.objects_json.exists() else []

    blocks = segment_into_mistake_blocks(transcript)
    if not blocks:
        print(f"No \"For step N, ...\" cues found in {paths.transcript_json} — nothing to fuse.")
        return

    matched, unmatched = 0, []
    for block in blocks:
        step = steps_by_index.get(block["step_index"])
        if step is None:
            unmatched.append(block["step_index"])
            continue
        mistake_text, correction_text = split_mistake_and_correction(block["text"])
        entry = {
            "mistake": mistake_text,
            "correction": correction_text,
            "source_session": paths.root.name,
            "reference_frame": frame_ref_for_block(block, objects),
        }
        common_mistakes = step.setdefault("common_mistakes", {"value": [], "source": None, "reviewed": False})
        common_mistakes.setdefault("value", [])
        common_mistakes["value"].append(entry)
        common_mistakes["source"] = "artisan_demo"
        # Real captured content, not synthesized — but still needs a human to
        # confirm it reads clearly before it reaches a learner.
        common_mistakes["reviewed"] = False
        matched += 1

    write_json(step_templates_path, template_set)
    print(f"Fused {matched} mistake-demo block(s) into {step_templates_path}")
    if unmatched:
        print(f"Warning: {len(unmatched)} block(s) referenced step(s) not in step_templates.json: {sorted(unmatched)}")


if __name__ == "__main__":
    main()
