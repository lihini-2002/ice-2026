"""LLM-based step segmentation — an alternative to fuse_steps.py's regex cue
matcher for sessions where the artisan didn't say the verbal step cue (see
docs/capture_protocol.md).

Sends the transcript text (not audio/video) to the Claude API and asks it to
partition the transcript segments into logical steps of the physical task.
This is the one place in the pipeline where data leaves the machine — the
rest (transcription, object detection, gaze/hand fusion) runs locally.

The model is asked to partition transcript *segment indices*, not invent new
timestamps, so returned step boundaries always land exactly on existing
segment start/end times — consistent with how attach_objects() and
attach_gaze_and_hand_targets() in fuse_steps.py key off segment timestamps.

Usage (library only — no CLI entry point):
    from llm_segment import segment_into_steps_llm, SegmentationError
"""

from __future__ import annotations

from common import Step

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are segmenting a transcribed narration of a craft-making tutorial into \
logical steps. The artisan was recorded describing what they were doing \
while making something by hand, and the audio was transcribed into \
timestamped segments.

Group the segments into a sequence of steps, where each step covers one \
distinct action or phase of the physical task (e.g. "preparing the paper", \
"making the base fold", "shaping the final piece"). Steps must:
- cover every segment exactly once, in order (no gaps, no overlaps, no \
  reordering)
- start at segment index 0 and end at the last segment index
- represent a meaningful change in physical activity, not just a pause or \
  filler word — don't create a new step for every sentence

Respond with the step boundaries as segment index ranges plus a short title \
for each step."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_index": {"type": "integer"},
                    "end_index": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["start_index", "end_index", "title"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}


class SegmentationError(RuntimeError):
    """Raised when the LLM segmenter fails to produce a usable partition."""


def _build_user_prompt(transcript: list[dict]) -> str:
    lines = [
        f"[{i}] ({seg['start_s']:.1f}-{seg['end_s']:.1f}) {seg['text']}"
        for i, seg in enumerate(transcript)
    ]
    return "Transcript segments:\n" + "\n".join(lines)


def _validate_partition(steps_raw: list[dict], n_segments: int) -> list[dict]:
    if not steps_raw:
        raise SegmentationError("model returned zero steps")

    ordered = sorted(steps_raw, key=lambda s: s["start_index"])
    expected_next = 0
    for s in ordered:
        start, end = s["start_index"], s["end_index"]
        if not (0 <= start <= end < n_segments):
            raise SegmentationError(f"step index out of range: {s}")
        if start != expected_next:
            raise SegmentationError(
                f"gap or overlap at index {expected_next}: next step starts at {start}"
            )
        expected_next = end + 1
    if expected_next != n_segments:
        raise SegmentationError(
            f"partition doesn't cover all segments: ends at {expected_next - 1}, "
            f"expected {n_segments - 1}"
        )
    return ordered


def segment_into_steps_llm(
    transcript: list[dict], model: str = DEFAULT_MODEL
) -> list[Step]:
    """Partition transcript segments into Steps using the Claude API.

    Raises SegmentationError on any invalid or malformed response, and lets
    anthropic API exceptions (auth, rate limit, connection, ...) propagate —
    callers should catch both and fall back to the regex segmenter.
    """
    if not transcript:
        return []

    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": _build_user_prompt(transcript)}],
    )

    if response.stop_reason == "refusal":
        raise SegmentationError("model refused to segment the transcript")

    import json

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise SegmentationError("no text content in model response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise SegmentationError(f"model returned invalid JSON: {e}") from e

    steps_raw = parsed.get("steps") if isinstance(parsed, dict) else None
    if not isinstance(steps_raw, list):
        raise SegmentationError(f"unexpected response shape: {parsed!r}")

    ordered = _validate_partition(steps_raw, len(transcript))

    steps: list[Step] = []
    for s in ordered:
        start, end, title = s["start_index"], s["end_index"], s["title"]
        segs = transcript[start : end + 1]
        narration = " ".join(seg["text"] for seg in segs)
        steps.append(
            Step(
                start_s=segs[0]["start_s"],
                end_s=segs[-1]["end_s"],
                narration=f"{title}. {narration}" if title else narration,
            )
        )
    return steps
