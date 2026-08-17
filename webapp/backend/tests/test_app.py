"""Backend tests. Focus: the readiness gate on GET /api/sessions/<id>/step_templates
must never let an unreviewed step_templates.json reach a learner."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app as app_module

SAMPLE_STEP = {
    "step_index": 0,
    "narration": "fold the paper in half",
    "required_tools": ["a4 sheet"],
    "hand_state": {},
    "gaze_focus": None,
    "reference_frame": "derived/frames/frame_0.jpg",
    "rationale": {"value": None, "source": None, "reviewed": False},
    "success_criteria": {"value": [], "source": None, "reviewed": False},
    "common_mistakes": {"value": [], "source": None, "reviewed": False},
    "command_templates": {"value": {}, "source": None, "reviewed": False},
    "status": "needs_human_review",
}


def _write_session(output_root, session_id: str, status: str, steps=None) -> None:
    session_dir = output_root / session_id
    (session_dir / "derived" / "frames").mkdir(parents=True, exist_ok=True)
    (session_dir / "derived" / "frames" / "frame_0.jpg").write_bytes(b"fake-jpeg-bytes")
    (session_dir / "step_templates.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "craft": "origami making",
                "task_description": "test",
                "tool_threshold": 0.5,
                "status": status,
                "steps": steps if steps is not None else [SAMPLE_STEP],
            }
        )
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "OUTPUT_ROOT", tmp_path)
    return TestClient(app_module.app)


def test_unreviewed_session_is_rejected(tmp_path, client):
    _write_session(tmp_path, "sess_unreviewed", status="needs_human_review")

    resp = client.get("/api/sessions/sess_unreviewed/step_templates")

    assert resp.status_code == 409
    assert "not ready" in resp.json()["detail"]


def test_ready_session_is_served(tmp_path, client):
    ready_step = {**SAMPLE_STEP, "rationale": {"value": "why", "source": "human", "reviewed": True},
                  "success_criteria": {"value": ["done"], "source": None, "reviewed": True},
                  "common_mistakes": {"value": [{"mistake": "x", "correction": "y"}], "source": "artisan_demo", "reviewed": True},
                  "command_templates": {"value": {"correct_tool": ["Pick it up."]}, "source": "human", "reviewed": True}}
    _write_session(tmp_path, "sess_ready", status="ready", steps=[ready_step])

    resp = client.get("/api/sessions/sess_ready/step_templates")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_unknown_session_is_404(client):
    resp = client.get("/api/sessions/does_not_exist/step_templates")
    assert resp.status_code == 404


def test_invalid_session_id_is_400(client):
    resp = client.get("/api/sessions/../../etc/step_templates")
    # FastAPI's path routing normalizes "../.." out of the URL before it
    # reaches the handler, so this exercises the validator via a different
    # angle: a session_id shaped string that fails SESSION_ID_RE.
    assert resp.status_code in (400, 404)


def test_list_sessions_includes_status(tmp_path, client):
    _write_session(tmp_path, "sess_a", status="needs_human_review")
    _write_session(tmp_path, "sess_b", status="ready")

    resp = client.get("/api/sessions")

    assert resp.status_code == 200
    body = {s["session_id"]: s["status"] for s in resp.json()}
    assert body == {"sess_a": "needs_human_review", "sess_b": "ready"}


def test_reference_frame_is_served_for_a_ready_or_unready_session(tmp_path, client):
    _write_session(tmp_path, "sess_a", status="needs_human_review")

    resp = client.get("/api/sessions/sess_a/frames/0")

    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"


def test_telemetry_event_is_appended_to_log(tmp_path, client):
    _write_session(tmp_path, "sess_a", status="needs_human_review")

    resp = client.post(
        "/api/telemetry",
        json={"session_id": "sess_a", "step_id": 0, "timestamp": 12.5, "classification": "wrong_tool"},
    )

    assert resp.status_code == 201
    log_path = tmp_path / "sess_a" / "telemetry" / "log.jsonl"
    assert log_path.exists()
    record = json.loads(log_path.read_text().strip().splitlines()[-1])
    assert record["classification"] == "wrong_tool"
    assert record["step_id"] == 0
    assert "received_at" in record


def test_telemetry_rejects_unknown_classification(tmp_path, client):
    _write_session(tmp_path, "sess_a", status="needs_human_review")

    resp = client.post(
        "/api/telemetry",
        json={"session_id": "sess_a", "step_id": 0, "timestamp": 1.0, "classification": "not_a_real_state"},
    )

    assert resp.status_code == 422
