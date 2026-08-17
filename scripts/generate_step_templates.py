"""Stage 6 (authoring): derive per-step coaching templates from a fused
session.json, for the downstream learning_runtime/ coaching app.

For each step, thresholds the frequency-ranked tools/hand_targets already
computed by fuse_steps.py into required_tools / hand_state, and takes the
top-ranked gaze target as gaze_focus. These four fields are mechanical
derivations and are always regenerated from session.json on every run.

rationale, success_criteria, common_mistakes, and command_templates are a
different kind of field: they require judgment about *why* a step matters,
*how* a novice would get it wrong, and *what* a coach should say — none of
which is reliably recoverable from a single artisan narrating alone. This
script leaves them null/empty with a "needs_human_review" marker rather than
inventing plausible-sounding text. --llm-draft can draft rationale and
command_templates from narration_text as a starting point, but every drafted
field is tagged reviewed: false, and the script refuses to mark a session
"ready" until a human (ideally the artisan) has reviewed and confirmed it.

success_criteria and common_mistakes are never LLM-drafted — see
docs/mistake_elicitation_protocol.md for how common_mistakes gets populated
from a real second recording, and learning_runtime/README.md for why these
fields specifically need human/artisan input.

Usage:
    python scripts/generate_step_templates.py output/<session_id>
    python scripts/generate_step_templates.py output/<session_id> --threshold 0.6
    python scripts/generate_step_templates.py output/<session_id> --llm-draft
    python scripts/generate_step_templates.py output/<session_id> --mark-ready
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from common import SessionPaths, load_json, write_json

DEFAULT_THRESHOLD = 0.5

# Mirrors learning_runtime/command_generator.py's COMMAND_CATEGORIES. Kept as
# a separate constant (not imported) — learning_runtime has no dependency on
# this offline pipeline.
COMMAND_CATEGORIES = (
    "orient",
    "confirm",
    "correct_tool",
    "correct_motion",
    "correct_sequence",
    "encourage",
    "safety",
)

# Matches the "label (72%)" strings fuse_steps.py writes into gaze_targets,
# used only as a fallback when a step predates gaze_target_frequencies.
_RANKED_LABEL_RE = re.compile(r"^(.*?)\s*\(\d+%\)$")

REQUIRED_REVIEW_FIELDS = ("rationale", "success_criteria", "common_mistakes", "command_templates")


@dataclass
class ReviewableField:
    """A field that needs human sign-off before a session can be "ready".

    source is None (never touched), "llm_draft" (drafted from narration via
    --llm-draft, unreviewed until a human flips `reviewed`), or a free-form
    string like "artisan_demo" for content pulled from a mistake-demo session
    (see docs/mistake_elicitation_protocol.md / fuse_mistake_demo.py).
    """

    value: Any
    source: str | None = None
    reviewed: bool = False


@dataclass
class StepTemplate:
    step_index: int
    narration: str
    required_tools: list[str] = field(default_factory=list)
    hand_state: dict[str, list[str]] = field(default_factory=dict)
    gaze_focus: str | None = None
    reference_frame: str | None = None
    rationale: ReviewableField = field(default_factory=lambda: ReviewableField(value=None))
    success_criteria: ReviewableField = field(default_factory=lambda: ReviewableField(value=[]))
    common_mistakes: ReviewableField = field(default_factory=lambda: ReviewableField(value=[]))
    command_templates: ReviewableField = field(default_factory=lambda: ReviewableField(value={}))
    status: str = "needs_human_review"


@dataclass
class StepTemplateSet:
    session_id: str
    craft: str
    task_description: str
    tool_threshold: float
    steps: list[StepTemplate] = field(default_factory=list)
    status: str = "needs_human_review"


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == {} or value == ""


def _ranked_labels_above_threshold(freqs: dict[str, float], threshold: float) -> list[str]:
    return [label for label, f in sorted(freqs.items(), key=lambda kv: -kv[1]) if f >= threshold]


def derive_required_tools(step: dict, threshold: float) -> list[str]:
    freqs = step.get("tool_frequencies") or {}
    if freqs:
        return _ranked_labels_above_threshold(freqs, threshold)
    # Session predates tool_frequencies (re-run fuse_steps.py to backfill it)
    # — fall back to the unranked tools_used list rather than dropping data.
    return list(step.get("tools_used") or [])


def derive_hand_state(step: dict, threshold: float) -> dict[str, list[str]]:
    freqs = step.get("hand_target_frequencies") or {}
    hand_state = {}
    for side, side_freqs in freqs.items():
        labels = _ranked_labels_above_threshold(side_freqs, threshold)
        if labels:
            hand_state[side] = labels
    return hand_state


def derive_gaze_focus(step: dict) -> str | None:
    freqs = step.get("gaze_target_frequencies") or {}
    if freqs:
        return max(freqs.items(), key=lambda kv: kv[1])[0]
    # Fallback for sessions predating gaze_target_frequencies: parse the
    # top-ranked "label (NN%)" display string, skipping the no-data sentinels.
    targets = step.get("gaze_targets") or []
    if not targets:
        return None
    top = targets[0]
    m = _RANKED_LABEL_RE.match(top)
    if m:
        return m.group(1)
    if top in ("no eye-gaze data in this step", "gaze not on a detected object", "no eye-gaze data available"):
        return None
    return top


def _reviewable_from_prior(prior_step: dict | None, key: str, empty_value: Any) -> ReviewableField:
    if prior_step is None:
        return ReviewableField(value=empty_value)
    prior_field = prior_step.get(key)
    if not isinstance(prior_field, dict):
        return ReviewableField(value=empty_value)
    value = prior_field.get("value")
    if value is None:
        value = empty_value
    return ReviewableField(value=value, source=prior_field.get("source"), reviewed=bool(prior_field.get("reviewed", False)))


def build_step_template(step_index: int, step: dict, threshold: float, prior_step: dict | None) -> StepTemplate:
    frame_refs = step.get("frame_refs") or []
    return StepTemplate(
        step_index=step_index,
        narration=step.get("narration", ""),
        required_tools=derive_required_tools(step, threshold),
        hand_state=derive_hand_state(step, threshold),
        gaze_focus=derive_gaze_focus(step),
        reference_frame=frame_refs[0] if frame_refs else None,
        rationale=_reviewable_from_prior(prior_step, "rationale", None),
        success_criteria=_reviewable_from_prior(prior_step, "success_criteria", []),
        common_mistakes=_reviewable_from_prior(prior_step, "common_mistakes", []),
        command_templates=_reviewable_from_prior(prior_step, "command_templates", {}),
    )


def _draft_with_llm(template: StepTemplate, craft: str, task_description: str) -> dict:
    """Draft rationale + command_templates text from narration_text via an
    LLM call. Imported lazily so --llm-draft is the only code path that
    requires the `anthropic` package."""
    import anthropic

    client = anthropic.Anthropic()
    schema = {
        "type": "object",
        "properties": {
            "rationale": {
                "type": "string",
                "description": "One short paragraph on why this step matters technically.",
            },
            "command_templates": {
                "type": "object",
                "properties": {cat: {"type": "array", "items": {"type": "string"}} for cat in COMMAND_CATEGORIES},
                "additionalProperties": False,
                "description": "1-2 short, spoken-style coaching sentences per category that apply to this step.",
            },
        },
        "required": ["rationale", "command_templates"],
        "additionalProperties": False,
    }
    prompt = (
        f"Craft: {craft}\n"
        f"Overall task: {task_description}\n"
        f"Step {template.step_index} narration (the artisan's own words, transcribed verbatim): "
        f"{template.narration!r}\n"
        f"Tools observed in this step: {template.required_tools}\n"
        f"Hand placement observed in this step: {template.hand_state}\n\n"
        "Draft (a) a one-paragraph rationale explaining why this step matters technically, and "
        "(b) short, second-person coaching command templates for a novice learner, grouped by the "
        f"given categories ({', '.join(COMMAND_CATEGORIES)}) — only fill in categories that genuinely "
        "apply to this step. Base everything only on the narration and observed tools/hand-placement "
        "above — do not invent technique details, safety hazards, or craft knowledge the narration "
        "doesn't support. These are drafts for a human reviewer, not final copy."
    )
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=2000,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def maybe_draft(template: StepTemplate, craft: str, task_description: str) -> None:
    needs_rationale = _is_empty(template.rationale.value) and template.rationale.source is None
    needs_commands = _is_empty(template.command_templates.value) and template.command_templates.source is None
    if not (needs_rationale or needs_commands):
        return
    try:
        draft = _draft_with_llm(template, craft, task_description)
    except Exception as exc:
        print(f"  step {template.step_index}: LLM draft failed ({exc}) — leaving fields empty", file=sys.stderr)
        return
    if needs_rationale:
        template.rationale = ReviewableField(value=draft["rationale"], source="llm_draft", reviewed=False)
    if needs_commands:
        # Drop empty categories the model left out rather than storing {}.
        commands = {cat: templates for cat, templates in draft["command_templates"].items() if templates}
        template.command_templates = ReviewableField(value=commands, source="llm_draft", reviewed=False)


def readiness_issues(steps: list[StepTemplate]) -> list[str]:
    issues = []
    for step in steps:
        for field_name in REQUIRED_REVIEW_FIELDS:
            rf: ReviewableField = getattr(step, field_name)
            if _is_empty(rf.value):
                issues.append(f"step {step.step_index}: {field_name} is empty")
            elif not rf.reviewed:
                issues.append(f"step {step.step_index}: {field_name} is unreviewed (source={rf.source})")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"minimum observed frequency (0-1) for a tool/hand-target to count as required (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--llm-draft",
        action="store_true",
        help="draft empty rationale/command_templates fields from narration_text via an LLM call (tagged reviewed: false)",
    )
    parser.add_argument(
        "--mark-ready",
        action="store_true",
        help="attempt to set the session status to 'ready'; refuses (nonzero exit) if any step has unreviewed or empty required fields",
    )
    args = parser.parse_args()

    paths = SessionPaths(args.session_dir)
    if not paths.session_json.exists():
        sys.exit(f"Missing {paths.session_json} — run fuse_steps.py first.")
    session = load_json(paths.session_json)

    existing = load_json(paths.step_templates_json) if paths.step_templates_json.exists() else None
    existing_steps_by_index = {s["step_index"]: s for s in existing["steps"]} if existing else {}

    steps = []
    for i, step in enumerate(session["steps"]):
        template = build_step_template(i, step, args.threshold, existing_steps_by_index.get(i))
        if args.llm_draft:
            maybe_draft(template, session["craft"], session["task_description"])
        steps.append(template)

    issues = readiness_issues(steps)
    if args.mark_ready:
        if issues:
            print(f"Refusing to mark {paths.root.name} ready — unresolved fields:")
            for issue in issues:
                print(f"  - {issue}")
            status = "needs_human_review"
        else:
            status = "ready"
    else:
        status = "needs_human_review" if issues else "ready"

    template_set = StepTemplateSet(
        session_id=session["session_id"],
        craft=session["craft"],
        task_description=session["task_description"],
        tool_threshold=args.threshold,
        steps=steps,
        status=status,
    )

    write_json(paths.step_templates_json, template_set)
    print(f"Wrote {len(steps)} step templates to {paths.step_templates_json} (status: {status})")
    if issues and not args.mark_ready:
        print(f"{len(issues)} field(s) still need human review before this session can be marked ready.")

    if args.mark_ready and issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
