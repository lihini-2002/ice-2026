# Mistake-Elicitation Protocol — Recording Common Novice Mistakes

Extends [capture_protocol.md](capture_protocol.md)'s approach to a second, short recording per
craft: instead of narrating the correct technique once, the artisan deliberately demonstrates 2-3
mistakes a novice commonly makes at each step, and narrates the correction. This is the source
data for the `common_mistakes` field in `step_templates.json` (see
[scripts/generate_step_templates.py](../scripts/generate_step_templates.py)) — a field that,
per [learning_runtime/README.md](../learning_runtime/README.md), cannot be reliably synthesized
from the primary single-take session alone.

**Prerequisite:** the primary session for this craft must already have a `step_templates.json`
(`python scripts/generate_step_templates.py output/<primary_session_id>`) — the mistake-demo
recording fuses *into* that file's `common_mistakes` fields; it does not create step templates of
its own.

## Recording the mistake-demo session

- Same equipment and setup as the primary session (see capture_protocol.md).
- Keep it short — 2-3 mistakes per step of the primary session is enough. This is not a full
  re-performance of the task.
- Before recording, the artisan should have the primary session's `session.md` (or the numbered
  step list) in front of them, so their step numbers line up with the primary session's.

### Narration ask (read this to the artisan)

> "For this recording, we want you to show mistakes a beginner would make, not the correct
> technique — like you're pointing out what to watch for. For each step you want to cover, start
> with 'For step `<number>`, a common mistake is...' — using the step numbers from the recording
> we already made — then show and describe the mistake. When you're ready to show the fix, say
> 'The correction is...' and demonstrate it. Do 2 or 3 mistakes per step you want to cover; you
> don't need to cover every step."

This gives [scripts/fuse_mistake_demo.py](../scripts/fuse_mistake_demo.py) the same kind of free,
reliable segmentation signal that the "Next, I..." cue gives `fuse_steps.py` for the primary
session — a spoken step number instead of an inferred step boundary, and an explicit
mistake/correction split instead of a single narration block.

## `meta.json` for a mistake-demo session

Same shape as the primary session's `meta.json` (see [meta.example.json](../meta.example.json)),
plus two fields:

```json
{
  "craft": "pottery — wheel throwing",
  "artisan_id": "artisan_001",
  "date": "2026-08-17",
  "task_description": "Common novice mistakes for throwing a small bowl",
  "known_tools": ["potter's wheel", "clay", "rib tool", "wire cutter", "sponge", "water bowl"],
  "session_type": "mistake_demo",
  "linked_step_template_session": "pottery_artisan_001_20260816"
}
```

- `session_type: "mistake_demo"` marks this as a mistake recording rather than a primary
  technique recording. `fuse_mistake_demo.py` refuses to run against a session whose `meta.json`
  doesn't have this set — it's a guard against accidentally fusing a primary session's transcript
  as if it were mistake content.
- `linked_step_template_session` is the `session_id` (i.e. the `output/<session_id>` directory
  name) of the **primary** session whose `step_templates.json` this recording's mistakes belong
  to. `fuse_mistake_demo.py` reads this to find `output/<linked_step_template_session>/step_templates.json`
  unless `--step-templates` is passed explicitly.

## Pipeline stages

`ingest_vrs.py`, `transcribe.py`, `extract_scene_objects.py`, and `extract_gaze_hand_targets.py`
run **unchanged** against a mistake-demo session directory — they only care about the `.vrs`
recording and `meta.json`'s `known_tools`, not `session_type`:

```bash
python scripts/ingest_vrs.py output/<mistake_session_id>
python scripts/transcribe.py output/<mistake_session_id>
python scripts/extract_scene_objects.py output/<mistake_session_id>
python scripts/extract_gaze_hand_targets.py output/<mistake_session_id>
```

The fusion stage is where mistake-demo sessions diverge: instead of `fuse_steps.py` (which
segments a transcript into a fresh list of steps and writes `session.json`), run
`fuse_mistake_demo.py`, which segments the transcript by explicit step number and appends into
the **existing** step_templates.json of the primary session:

```bash
python scripts/fuse_mistake_demo.py output/<mistake_session_id>
# or, to override the linked session:
python scripts/fuse_mistake_demo.py output/<mistake_session_id> --step-templates output/<primary_session_id>/step_templates.json
```

`fuse_mistake_demo.py` does **not** write `output/<mistake_session_id>/session.json` — a
mistake-demo recording isn't a knowledge-base entry on its own, it's an addendum to the primary
session's step templates. Each matched "For step N..." block becomes one entry in that step's
`common_mistakes.value` list:

```json
{"mistake": "pressing off-center", "correction": "press evenly with both palms until the wobble stops", "source_session": "pottery_mistakes_artisan_001_20260817", "reference_frame": "derived/frames/frame_000004.100.jpg"}
```

`common_mistakes.source` is set to `"artisan_demo"` (distinct from `"llm_draft"` — see
`generate_step_templates.py`) and `reviewed` stays `false`: this is real captured content from the
artisan, not synthesized, but a human should still read it over for clarity/completeness before a
learner sees it. Re-running `generate_step_templates.py` on the primary session afterward will
**not** clobber it — that script only ever regenerates `required_tools` / `hand_state` /
`gaze_focus` / `reference_frame` from `session.json`; the four review-gated fields (including
`common_mistakes`) are always carried forward from the existing `step_templates.json`.

## Known limits

- Step-number matching is exact and manual: if the artisan says "step 3" but means the fourth
  entry in `step_templates.json` (because they're eyeballing `session.md`'s 1-indexed numbering
  against `step_templates.json`'s 0-indexed `step_index`), the mistake lands on the wrong step.
  `fuse_mistake_demo.py` warns (but does not fail) when a cued step number has no matching
  `step_index` in `step_templates.json` — always check its "Warning: ... referenced step(s) not
  in step_templates.json" output.
- Like the primary capture protocol, this relies entirely on the artisan remembering the verbal
  cues. A mistake demonstrated without the "For step N..." / "The correction is..." phrasing is
  silently dropped (it never starts a block, or its correction text is left as `null`).
- One mistake-demo recording is expected to cover one primary session. If a craft has multiple
  primary sessions (different artisans, different task variations), record and fuse a separate
  mistake-demo session per primary session.
