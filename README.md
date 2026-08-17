# ice-2026

A pilot pipeline that turns a [Project Aria](https://www.projectaria.com/) glasses recording of an
artisan performing a craft into a structured, searchable knowledge-base entry documenting the
technique — narration, tools/materials used, and what the artisan was looking at / holding at
each step.

**Pilot scope:** one artisan, one craft, one continuous session. See
[docs/capture_protocol.md](docs/capture_protocol.md) for the full recording protocol and its
known limitations.

## How it works

1. **Capture** — an artisan wears Aria glasses and narrates the task aloud, using a verbal cue
   ("Next, I..." / "Now I'm going to...") to mark the start of each step. See
   [docs/capture_protocol.md](docs/capture_protocol.md).
2. **Ingest** ([scripts/ingest_vrs.py](scripts/ingest_vrs.py)) — pulls the audio track and samples
   RGB frames out of the `.vrs` recording.
3. **Transcribe** ([scripts/transcribe.py](scripts/transcribe.py)) — local `faster-whisper`
   transcription of the narration, timestamped. No audio leaves the machine.
4. **Detect objects** ([scripts/extract_scene_objects.py](scripts/extract_scene_objects.py)) —
   zero-shot OWLv2 object detection on sampled frames, prompted with the craft's tool/material
   vocabulary from `meta.json`.
5. **Link gaze/hands** ([scripts/extract_gaze_hand_targets.py](scripts/extract_gaze_hand_targets.py))
   — projects Meta MPS eye-gaze and hand-tracking output into the RGB image plane and matches it
   against the detected object boxes, linking "looking at X" / "holding Y" to each moment.
6. **Fuse** ([scripts/fuse_steps.py](scripts/fuse_steps.py)) — splits the transcript into steps
   using the narration cue, attaches tools/gaze/hand data to each step, and writes
   `session.json` (machine-readable) + `session.md` (human-readable).

[scripts/run_pipeline.py](scripts/run_pipeline.py) chains all five stages.
[scripts/common.py](scripts/common.py) holds the shared session layout and dataclasses.

## Downstream: teaching a novice from a captured session

Two additions build a learning experience on top of a session's `session.json`:

7. **Generate step templates** ([scripts/generate_step_templates.py](scripts/generate_step_templates.py))
   — thresholds each step's frequency-ranked tools/hand targets into `required_tools`/`hand_state`,
   and writes `step_templates.json`. Fields that need human/artisan judgment (`rationale`,
   `success_criteria`, `common_mistakes`, `command_templates`) are left `null`/empty and marked
   `needs_human_review` rather than invented — see
   [learning_runtime/README.md](learning_runtime/README.md) for why, and
   [docs/mistake_elicitation_protocol.md](docs/mistake_elicitation_protocol.md) for how
   `common_mistakes` gets filled from a real second recording of common novice mistakes.
8. **Real-time coaching runtime** ([learning_runtime/](learning_runtime/)) — a separate module
   (no `projectaria-tools`/VRS dependency) that watches a learner via a top-mounted RGB camera
   (MediaPipe Hands + an object detector, no gaze/hand-tracking hardware on the learner side) and
   gives audio + visual corrections against a `step_templates.json`. See its README for the module
   map and the offline-video-first testing workflow.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`torch` and `transformers` are the heaviest dependencies (a few GB) — OWLv2 runs on CPU by
default but will use CUDA if available.

## Running a session

1. Follow [docs/capture_protocol.md](docs/capture_protocol.md) to record and export a session.
2. Lay out the session directory:

   ```
   output/<session_id>/
       meta.json          # see meta.example.json
       raw/<name>.vrs      # exported Aria recording
       mps/                # optional — MPS eye-gaze/hand-tracking results
   ```

3. Run the pipeline:

   ```bash
   python scripts/run_pipeline.py output/<session_id>
   ```

   Individual stages can be skipped (e.g. to re-run only the fusion step after tweaking data):

   ```bash
   python scripts/run_pipeline.py output/<session_id> --skip ingest_vrs.py transcribe.py extract_scene_objects.py
   ```

4. Read the result at `output/<session_id>/session.md` (or `session.json` for the structured
   version).

`output/` is git-ignored — recordings and derived data (including proprietary craft technique)
are never committed. See the data-handling note in
[docs/capture_protocol.md](docs/capture_protocol.md) before submitting a recording to Meta's MPS
cloud service.

## Repo layout

```
docs/capture_protocol.md              # how to record a session
docs/mistake_elicitation_protocol.md  # how to record a second "common novice mistakes" session
meta.example.json                     # template for output/<session_id>/meta.json
requirements.txt                      # Python dependencies (offline pipeline)
scripts/                              # pipeline stages (see "How it works" above)
learning_runtime/                     # real-time coaching runtime (see its own README)
output/                               # git-ignored — session recordings and derived data live here
```
