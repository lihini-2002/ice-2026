"""Thin backend for the learner-facing web app.

This server does NOT run any ML inference — perception, step-tracking,
comparison, and command generation all run client-side in the browser (see
webapp/frontend/). Its only two jobs:

1. Serve step_templates.json (and each step's reference frame image) for a
   given session — refusing to serve a session whose templates aren't yet
   "ready" (see scripts/generate_step_templates.py's --mark-ready gate), so
   an unreviewed, possibly-wrong coaching template never reaches a learner.
2. Accept learner telemetry (comparator-state events) and append them to a
   per-session log under output/<session_id>/telemetry/ — raw material for
   a human to later expand common_mistakes (see
   docs/mistake_elicitation_protocol.md), not something this endpoint
   writes back into step_templates.json itself.

Reuses scripts/common.py's SessionPaths for the output/<session_id>/ layout
rather than re-deriving it — that module has no heavy dependencies
(projectaria-tools et al. are only imported by the VRS-handling scripts, not
common.py itself), so it's safe to import here.

Usage:
    uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from common import SessionPaths, load_json  # noqa: E402

OUTPUT_ROOT = REPO_ROOT / "output"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

app = FastAPI(title="ice-2026 learning webapp backend")

# Permissive CORS for local dev (frontend on a different Vite port). Tighten
# this to the actual frontend origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _session_paths(session_id: str) -> SessionPaths:
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    paths = SessionPaths(OUTPUT_ROOT / session_id)
    if not paths.root.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown session_id: {session_id}")
    return paths


@app.get("/api/sessions")
def list_sessions():
    """Lists sessions that have a step_templates.json at all (regardless of
    review status) — the frontend's session-select screen shows status so a
    learner can see why a session they picked isn't playable yet, rather
    than the session silently not appearing."""
    sessions = []
    if OUTPUT_ROOT.is_dir():
        for session_dir in sorted(p for p in OUTPUT_ROOT.iterdir() if p.is_dir()):
            paths = SessionPaths(session_dir)
            if not paths.step_templates_json.exists():
                continue
            data = load_json(paths.step_templates_json)
            sessions.append(
                {
                    "session_id": data.get("session_id", session_dir.name),
                    "craft": data.get("craft"),
                    "task_description": data.get("task_description"),
                    "status": data.get("status"),
                    "step_count": len(data.get("steps", [])),
                }
            )
    return sessions


@app.get("/api/sessions/{session_id}/step_templates")
def get_step_templates(session_id: str):
    paths = _session_paths(session_id)
    if not paths.step_templates_json.exists():
        raise HTTPException(
            status_code=404,
            detail=f"step_templates.json not generated yet for '{session_id}' — run scripts/generate_step_templates.py",
        )
    data = load_json(paths.step_templates_json)
    if data.get("status") != "ready":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Session '{session_id}' is not ready for learner use (status={data.get('status')!r}). "
                "A human needs to fill in and review rationale/success_criteria/common_mistakes/"
                "command_templates, then run scripts/generate_step_templates.py --mark-ready."
            ),
        )
    return data


@app.get("/api/sessions/{session_id}/frames/{step_id}")
def get_reference_frame(session_id: str, step_id: int):
    paths = _session_paths(session_id)
    if not paths.step_templates_json.exists():
        raise HTTPException(status_code=404, detail=f"step_templates.json not generated yet for '{session_id}'")
    data = load_json(paths.step_templates_json)
    step = next((s for s in data.get("steps", []) if s.get("step_index") == step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail=f"No step {step_id} in session '{session_id}'")
    ref = step.get("reference_frame")
    if not ref:
        raise HTTPException(status_code=404, detail=f"Step {step_id} has no reference_frame")

    session_root = paths.root.resolve()
    frame_path = (paths.root / ref).resolve()
    if not frame_path.is_relative_to(session_root) or not frame_path.is_file():
        raise HTTPException(status_code=404, detail="Reference frame not found")
    return FileResponse(frame_path)


class TelemetryEvent(BaseModel):
    session_id: str
    step_id: int
    timestamp: float
    classification: Literal["on_track", "wrong_tool", "wrong_hand_state", "wrong_sequence", "step_complete"]
    note: str | None = None


@app.post("/api/telemetry", status_code=201)
def post_telemetry(event: TelemetryEvent):
    paths = _session_paths(event.session_id)
    telemetry_dir = paths.root / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    record = event.model_dump()
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    # Append-only JSON Lines — avoids the read-modify-write race a single
    # JSON array would have under concurrent POSTs from one learner session.
    with open(telemetry_dir / "log.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

    return {"status": "logged"}
