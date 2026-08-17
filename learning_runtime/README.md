# learning_runtime — Real-Time Coaching Runtime

Consumes `step_templates.json` (written by
[scripts/generate_step_templates.py](../scripts/generate_step_templates.py)) and a stream of
perception output from a top-mounted RGB camera on the *learner* side, and produces audio +
visual coaching corrections. This is a separate module from the offline authoring pipeline in
`scripts/` — **no dependency on projectaria-tools or VRS files** — so it can run on a laptop, a
phone, or an edge device without pulling in the Aria SDK.

**Scope of this pass:** template-generation stage, protocol doc, and this runtime, tested against
recorded video only (`run_offline_test.py`). No mobile app UI, no live camera capture, no real
TTS — those are wired in later by the mobile app against the `DeliveryChannel` interface in
`delivery.py`.

## No gaze/hand-tracking hardware on the learner side

The offline pipeline (Aria glasses on the *artisan*) has continuous eye gaze and hand-tracking
data from Meta's MPS service. The learner side has none of that — only a top-mounted RGB camera,
MediaPipe Hands, and a fine-tuned/distilled object detector. There is **no continuous hand
pose/trajectory stream** to compare against, only discrete "hand touching/holding object X"
contact events per frame (see `perception.py`'s `infer_contacts`).

Every design choice downstream follows from that constraint:

- `step_tracker.py` tracks the active step via a sliding-window vote over per-frame contact-state
  matches, not motion-trajectory matching — the same frequency-ranking philosophy
  `scripts/fuse_steps.py` uses offline (rank tools/targets by how often they're observed, not by
  trusting any single sample).
- `comparator.py` classifies against `required_tools` / `hand_state` contact sets, explicitly and
  rule-based rather than as a black-box model — so a developer can step through *why* a frame was
  classified a given way against real footage, instead of debugging a model's internals.

## Module map

| Module | Responsibility |
| --- | --- |
| `perception.py` | Wraps an `ObjectDetector` (interface — swap in a real fine-tuned/distilled model) + MediaPipe Hands. Outputs `PerceptionFrame`: detected objects with boxes, hand landmarks, and inferred hand-to-object contacts. |
| `step_tracker.py` | State machine tracking which step of `step_templates.json` the learner is likely attempting, via sliding-window plurality vote over `perception.py`'s contact output. |
| `comparator.py` | Given the current perception state + the active step template, classifies into `on_track` / `wrong_tool` / `wrong_hand_state` / `wrong_sequence` / `step_complete` / `no_evidence`. Simple, explicit, rule-based. |
| `command_generator.py` | Taxonomy of command categories (`orient`, `confirm`, `correct_tool`, `correct_motion`, `correct_sequence`, `encourage`, `safety`), slot-filled from `step_templates.json`'s `command_templates`, with debouncing so the same correction isn't repeated every frame. Falls back to a generic narration-based sentence — with a logged warning — when a step's `command_templates` are empty or not yet human-reviewed. |
| `delivery.py` | `DeliveryChannel` interface for audio (TTS) + visual (bounding box / step-progress overlay) output. `PrintDeliveryChannel` is a print-based mock; the mobile app implements the real thing later. |
| `run_offline_test.py` | Entry point that runs the whole runtime against a **pre-recorded learner video file**. This is the first thing to run and inspect before any live-camera integration. |
| `step_templates.py` | Standalone loader for `step_templates.json` — deliberately duplicates the offline schema instead of importing `scripts/common.py`, so this module has zero dependency on the offline pipeline. |

## Testing workflow — offline before live

1. **Unit tests first** (`tests/`) — `step_tracker.py` and `comparator.py` against synthetic
   `step_templates.json` fixtures and synthetic `PerceptionFrame` sequences, no camera or model
   required:

   ```bash
   python3 -m unittest discover -s learning_runtime/tests -t .
   ```

2. **Offline video validation** — once a real `ObjectDetector` is wired in, run the full loop
   against a pre-recorded learner video *before* touching a live camera:

   ```bash
   pip install -r learning_runtime/requirements.txt
   python -m learning_runtime.run_offline_test <video_path> output/<session_id>/step_templates.json
   ```

   `run_offline_test.py` defaults to `StubObjectDetector`, which raises as soon as detection is
   requested — pass a real `ObjectDetector` via `run(..., detector=...)` when calling it as a
   library. This ordering is deliberate: recorded video is repeatable and debuggable frame-by-frame
   in a way a live camera feed isn't, so it's the right place to shake out perception/tracking/
   comparator bugs first.

3. **Live camera** is out of scope for this pass — not implemented.

## Fields that need human/artisan input and cannot be automated

`scripts/generate_step_templates.py` deliberately leaves four fields null/empty with a
`"status": "needs_human_review"` marker rather than synthesizing them from a single artisan
narration. **Three of them cannot be filled in from a single-session capture at all**, no matter
how good the narration or an LLM draft is:

- **`rationale`** — *why* a step matters technically. `--llm-draft` can produce a plausible-sounding
  draft from the narration text, but it's tagged `"source": "llm_draft", "reviewed": false` until a
  human — ideally the artisan — confirms it's actually correct technique reasoning and not a
  plausible-sounding guess.
- **`success_criteria`** — how a coach (human or this runtime) tells the step was actually done
  correctly. A single narrated take doesn't reliably state this; it has to be written by someone
  who knows the craft.
- **`common_mistakes`** — what a *novice*, not the expert performing the primary session, gets
  wrong. An artisan doing the task correctly on camera doesn't demonstrate the failure modes a
  beginner hits. This is why [docs/mistake_elicitation_protocol.md](../docs/mistake_elicitation_protocol.md)
  exists as a **second recording**: the artisan deliberately performs and narrates 2-3 common
  novice mistakes per step. `scripts/fuse_mistake_demo.py` fuses that into `common_mistakes`
  tagged `"source": "artisan_demo"` — real captured content, not synthesized, but still marked
  `"reviewed": false` until a human confirms it reads clearly.

`command_templates` is the one review-gated field that *can* be LLM-drafted from narration
(`--llm-draft`), but `command_generator.py` never delivers a draft that hasn't been marked
`reviewed: true` — see the fallback behavior above. `required_tools`, `hand_state`, `gaze_focus`,
and `reference_frame` are the opposite case: they're mechanically derived by thresholding the
frequency-ranked data already in `session.json`, need no human judgment, and are regenerated
fresh every time `generate_step_templates.py` runs.

`scripts/generate_step_templates.py --mark-ready` refuses (nonzero exit) to mark a session ready
while any step still has an empty or unreviewed `rationale` / `success_criteria` /
`common_mistakes` / `command_templates` — this runtime should never be pointed at a
`step_templates.json` whose top-level `"status"` isn't `"ready"`.
