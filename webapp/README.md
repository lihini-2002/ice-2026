# webapp — Browser-Based Coaching Runtime

A web port of [`learning_runtime/`](../learning_runtime/)'s real-time coaching logic, for a
learner-facing web app instead of a native mobile app. Consumes the exact same
`step_templates.json` artifacts the offline pipeline produces (see
[scripts/generate_step_templates.py](../scripts/generate_step_templates.py)) — nothing about the
authoring side changes.

## How this relates to `learning_runtime/`

`learning_runtime/` is not superseded by this — it's the **reference implementation** this port
was built against, and it stays useful for two things this web app can't do:

- **Validating logic before porting.** Every module here (`stepTracker.js`, `comparator.js`,
  `commandGenerator.js`) is a line-for-line port of the corresponding Python module
  (`step_tracker.py`, `comparator.py`, `command_generator.py`) — same sliding-window vote, same
  rule-based classification states, same debounce/fallback behavior. `webapp/frontend/test/`
  mirrors `learning_runtime/tests/` against equivalent fixtures precisely so the two
  implementations can be checked against each other; if a future change to one isn't mirrored in
  the other, the tests are where that gap would need to be caught (there's no automated
  cross-check between the two languages — keep them in sync by hand).
- **Offline batch-testing against recorded video, no browser required.**
  `learning_runtime/run_offline_test.py` runs the whole loop against a video file headlessly —
  useful for CI, for testing on a machine with no camera, or for quickly iterating on a
  `step_templates.json` without a browser in the loop at all.

Perception is the one module that isn't a mechanical port — `perception.py` wraps MediaPipe
Python + a Python `ObjectDetector`; `perception.js` wraps MediaPipe Tasks Vision (JS/WASM) + a
JS `ObjectDetector`, both structured around the *same output shape* (`PerceptionFrame`: objects
with boxes, hand landmarks, inferred hand-to-object contacts) so the downstream logic didn't need
to be redesigned, only re-expressed. The one real behavioral difference: browser ML inference is
inherently asynchronous (model loading, WASM/WebGL), so `ObjectDetector.detect()` and
`Perception.processFrame()` return Promises where the Python versions are synchronous calls.

## Architecture

- **All real-time inference runs client-side**, in the browser (WASM/JS) — perception,
  step-tracking, comparison, and command generation. No per-frame server round-trip.
- **The backend is inference-free.** It serves `step_templates.json` + reference frame images,
  and logs learner telemetry. That's it — see [`backend/app.py`](backend/app.py).
- **Visual overlay is 2D canvas only** in this pass (`overlay.js`'s `Canvas2DOverlay`), behind an
  `OverlayRenderer` interface. A three.js-based 3D hand-orientation overlay is explicitly
  deferred to a later phase — `step_templates.json` only carries discrete contact events (e.g.
  "holding a4 sheet"), not continuous hand-pose/orientation data, so there's nothing for a 3D
  overlay to visualize yet. When that data exists, a `ThreeJsOverlay` class implementing the same
  `.draw(state)` contract can drop in without touching `comparator.js`/`commandGenerator.js`.
- **Audio is the Web Speech API** (`speechSynthesis`) — no external TTS service, no API key, no
  network dependency for coaching speech.

## Directory layout

```
webapp/
  backend/
    app.py                  # FastAPI app — the three endpoints below
    requirements.txt
    tests/test_app.py       # readiness-gate test + endpoint coverage
  frontend/
    index.html
    vite.config.js
    package.json
    src/
      perception.js         # MediaPipe Tasks Vision + ObjectDetector interface + contact inference
      stepTemplates.js      # step_templates.json loader (mirrors learning_runtime/step_templates.py)
      stepTracker.js        # port of step_tracker.py
      comparator.js         # port of comparator.py
      commandGenerator.js   # port of command_generator.py
      overlay.js            # 2D canvas rendering, behind an OverlayRenderer interface
      audio.js              # Web Speech API wrapper, priority-ordered
      main.js              # wiring: camera -> perception -> tracker -> comparator -> commander -> overlay/audio
    test/                    # vitest — mirrors learning_runtime/tests/
```

## Backend API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/sessions` | List sessions that have a `step_templates.json`, with their review `status`, for the session-select screen. |
| `GET /api/sessions/{session_id}/step_templates` | Serve the JSON for one session. **409** if `status != "ready"` — see `scripts/generate_step_templates.py --mark-ready`. An unreviewed template never reaches a learner. |
| `GET /api/sessions/{session_id}/frames/{step_id}` | Serve that step's `reference_frame` image. |
| `POST /api/telemetry` | Accepts `{session_id, step_id, timestamp, classification, note?}` and appends it to `output/<session_id>/telemetry/log.jsonl`. Raw material for a human to later expand `common_mistakes` (see [docs/mistake_elicitation_protocol.md](../docs/mistake_elicitation_protocol.md)) — **this endpoint never writes back into `step_templates.json` itself.** |

`classification` is one of `on_track` / `wrong_tool` / `wrong_hand_state` / `wrong_sequence` /
`step_complete` — `no_evidence` frames aren't posted (nothing informative to log about silence,
same reasoning `commandGenerator.js` uses to skip generating a command for them).

## Running locally

**Backend:**

```bash
cd webapp/backend
python3 -m venv .venv && source .venv/bin/activate   # or reuse the repo-root .venv
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

**Frontend** (separate terminal):

```bash
cd webapp/frontend
npm install
npm run dev
```

Vite's dev server proxies `/api/*` to `localhost:8000` (see `vite.config.js`), so no CORS
configuration is needed in dev; `app.py` also sets permissive CORS headers directly for
non-proxied cases. Open the printed `localhost` URL, pick a session, and the coaching screen
requests camera access.

**Tests:**

```bash
# Backend
cd webapp/backend && python3 -m pytest tests/ -v

# Frontend
cd webapp/frontend && npm test
```

## Model files needed before live camera testing works

Nothing in this pass ships a trained model — same "assume a placeholder model" scope as
`learning_runtime/perception.py`'s `StubObjectDetector`. Two files need to be supplied under
`webapp/frontend/public/` (gitignored — see `.gitignore`) before `npm run dev` produces a working
camera loop rather than an immediate error:

1. **`public/models/hand_landmarker.task`** — a MediaPipe hand-landmarker model. Download one
   from Google's MediaPipe model zoo (the standard `hand_landmarker.task` works as-is — this repo
   doesn't need a custom-trained hand model, only the standard one).
2. **`public/mediapipe/wasm/`** — the MediaPipe Tasks Vision WASM fileset (matching whatever
   `@mediapipe/tasks-vision` version is pinned in `package.json`). Copy it from
   `node_modules/@mediapipe/tasks-vision/wasm/` after `npm install`, or point
   `MediaPipeHandTracker.create({ wasmBasePath: ... })` at a CDN URL instead if self-hosting isn't
   a requirement for your deployment.
3. **An `ObjectDetector` implementation** — `perception.js` ships only `StubObjectDetector`,
   which throws as soon as detection is requested (same as the Python reference). A real one
   needs a **fine-tuned/distilled model matching the offline pipeline's OWLv2 vocabulary**
   (see [scripts/extract_scene_objects.py](../scripts/extract_scene_objects.py)), served via
   TensorFlow.js (`tf.loadGraphModel`) or ONNX Runtime Web (`ort.InferenceSession`), wrapped in a
   class implementing `perception.js`'s `ObjectDetector` interface (`async detect(frame,
   vocabulary) -> DetectedObject[]`) and passed to `startSession(sessionId, { detector })` in
   `main.js`. Training/fine-tuning that model is explicitly out of scope for this pass.

Without (3), the session-select screen and the readiness-gated `step_templates.json` fetch all
work — only the live camera loop's object-detection half is a stub. Hand tracking (MediaPipe) and
step-tracking/comparison/command-generation are all real and testable today (see `test/`), the
same "offline-first" order the Python reference recommends: unit tests first, then perception
against real input once a model exists, live camera last.

## Not built in this pass

- **three.js / 3D overlay** — interface only (`OverlayRenderer` in `overlay.js`); deferred until
  `step_templates.json` carries continuous hand-pose/orientation data to visualize.
- **Object-detector training/fine-tuning** — a placeholder (`StubObjectDetector`) stands in; see
  "Model files needed" above.
- **A human-review UI** for `rationale` / `success_criteria` / `common_mistakes` /
  `command_templates` — that's a separate authoring-side tool, not part of this learner-facing
  app. Today those fields are reviewed by hand-editing `step_templates.json` and re-running
  `scripts/generate_step_templates.py --mark-ready`.
