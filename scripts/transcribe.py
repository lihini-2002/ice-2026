"""Stage 2: transcribe the narration audio into timestamped segments.

Runs locally via faster-whisper — no audio leaves the machine.

Usage:
    python scripts/transcribe.py <session_id>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SessionPaths, TranscriptSegment, write_json

# "base"/"small" are fast enough for a pilot on CPU; bump to "medium"/"large-v3"
# once accuracy on craft-specific vocabulary (tool names) needs improving.
WHISPER_MODEL_SIZE = "small"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--model-size", default=WHISPER_MODEL_SIZE)
    args = parser.parse_args()

    paths = SessionPaths(args.session_id)
    audio_path = paths.derived_dir / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"{audio_path} not found — run ingest_vrs.py first.")

    from faster_whisper import WhisperModel

    print(f"Loading whisper model '{args.model_size}' ...")
    model = WhisperModel(args.model_size, device="cpu", compute_type="int8")

    print(f"Transcribing {audio_path} ...")
    segments, info = model.transcribe(str(audio_path), vad_filter=True)

    out_segments = [
        TranscriptSegment(start_s=seg.start, end_s=seg.end, text=seg.text.strip())
        for seg in segments
    ]

    write_json(paths.transcript_json, [s.__dict__ for s in out_segments])
    print(f"Wrote {len(out_segments)} transcript segments to {paths.transcript_json}")


if __name__ == "__main__":
    main()
