"""Stage 2: transcribe the narration audio into timestamped segments.

Runs locally via faster-whisper — no audio leaves the machine.

Usage:
    python scripts/transcribe.py output/<session_id>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SessionPaths, TranscriptSegment, load_json, write_json

# "base"/"small" are fast enough for a pilot on CPU; bump to "medium"/"large-v3"
# once accuracy on craft-specific vocabulary (tool names) needs improving.
WHISPER_MODEL_SIZE = "small"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--model-size", default=WHISPER_MODEL_SIZE)
    args = parser.parse_args()

    paths = SessionPaths(args.session_dir)
    audio_path = paths.derived_dir / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"{audio_path} not found — run ingest_vrs.py first.")

    # audio.wav itself has no timestamp metadata (playback always starts at
    # sample 0), but frames/objects/gaze/hand samples are all timestamped on
    # the recording's absolute device clock (see ingest_vrs.py). Without this
    # offset, fuse_steps.py would compare transcript segments against frame
    # timestamps on two different clocks and silently match nothing.
    if paths.audio_start_time_json.exists():
        audio_start_s = load_json(paths.audio_start_time_json)["audio_start_s"]
    else:
        audio_start_s = 0.0
        print(
            f"Warning: {paths.audio_start_time_json} not found — assuming a 0s offset. "
            "Transcript timestamps may not line up with frame/object timestamps; "
            "re-run ingest_vrs.py to regenerate it."
        )

    from faster_whisper import WhisperModel

    print(f"Loading whisper model '{args.model_size}' ...")
    model = WhisperModel(args.model_size, device="cpu", compute_type="int8")

    print(f"Transcribing {audio_path} ...")
    segments, info = model.transcribe(str(audio_path), vad_filter=True)

    out_segments = [
        TranscriptSegment(start_s=seg.start + audio_start_s, end_s=seg.end + audio_start_s, text=seg.text.strip())
        for seg in segments
    ]

    write_json(paths.transcript_json, [s.__dict__ for s in out_segments])
    print(f"Wrote {len(out_segments)} transcript segments to {paths.transcript_json}")


if __name__ == "__main__":
    main()
