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
2. Lay out the input session directory:

   ```
   videos/<session_id>/
       meta.json          # see meta.example.json
       raw/<name>.vrs      # exported Aria recording
       mps/                # optional — MPS eye-gaze/hand-tracking results
   ```

3. Run the pipeline:

   ```bash
   python scripts/run_pipeline.py <session_id>
   ```

   Individual stages can be skipped (e.g. to re-run only the fusion step after tweaking data):

   ```bash
   python scripts/run_pipeline.py <session_id> --skip ingest_vrs.py transcribe.py extract_scene_objects.py
   ```

4. Read the result at `outputs/<session_id>/session.md` (or `session.json` for the structured
   version).

`videos/` and `outputs/` are git-ignored — recordings and derived data (including proprietary
craft technique) are never committed. See the data-handling note in
[docs/capture_protocol.md](docs/capture_protocol.md) before submitting a recording to Meta's MPS
cloud service.

## Repo layout

```
docs/capture_protocol.md   # how to record a session
meta.example.json          # template for videos/<session_id>/meta.json
requirements.txt           # Python dependencies
scripts/                   # pipeline stages (see "How it works" above)
videos/                    # git-ignored — input: raw .vrs recordings, meta.json, MPS results
outputs/                   # git-ignored — output: per-session pipeline results live here
```
