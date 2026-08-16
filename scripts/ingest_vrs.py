"""Stage 1: load the .vrs recording and pull out the audio track for
transcription plus sampled RGB frames for object detection.

Usage:
    python scripts/ingest_vrs.py <session_id>
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
from PIL import Image
from projectaria_tools.core import data_provider

from common import SessionPaths

RGB_CAMERA_LABEL = "camera-rgb"
AUDIO_LABEL = "mic"

# Sample one frame every N seconds for object detection — dense enough to
# catch tool changes without dumping thousands of near-duplicate frames.
FRAME_SAMPLE_INTERVAL_S = 2.0


def extract_audio(provider: "data_provider.VrsDataProvider", out_wav: Path) -> None:
    stream_id = provider.get_stream_id_from_label(AUDIO_LABEL)
    if stream_id is None:
        raise RuntimeError("No audio stream found in this VRS — narration transcription needs the mic stream.")

    # Sample rate and channel count live on the stream's audio configuration,
    # not on each per-record AudioData (which only exposes `data`/`max_amplitude`).
    config = provider.get_audio_configuration(stream_id)
    sample_rate = config.sample_rate
    num_channels = config.num_channels

    num_data = provider.get_num_data(stream_id)
    frames = []
    for i in range(num_data):
        audio_data, _record = provider.get_audio_data_by_index(stream_id, i)
        # Aria mic samples come back as plain Python ints wider than 16 bits
        # (observed as 24-bit audio left-shifted into a 32-bit word) — int32
        # is the safe container; forcing int16 here overflows.
        frames.append(np.array(audio_data.data, dtype=np.int32))

    if not frames:
        raise RuntimeError("Audio stream was present but contained no samples.")

    interleaved = np.concatenate(frames)
    # Aria's mic array has multiple channels (e.g. 7-mic array); interleaved
    # samples are (frame, channel). Downmix to mono for transcription.
    interleaved = interleaved[: len(interleaved) - (len(interleaved) % num_channels)]
    mono32 = interleaved.reshape(-1, num_channels).mean(axis=1) if num_channels > 1 else interleaved.astype(np.float64)
    # Scale to int16 range based on the actual observed peak rather than
    # assuming a fixed bit depth — different Aria units/firmware have been
    # observed reporting mic samples at different effective bit depths, and
    # blindly right-shifting (e.g. dividing by 256 assuming 24-bit-in-32-bit)
    # can crush a recording that's already within int16 range down to
    # near-silence, which then makes downstream VAD-based transcription
    # detect no speech at all.
    peak = np.abs(mono32).max()
    if peak > 32767:
        mono32 = mono32 * (32767.0 / peak)
    pcm = np.clip(mono32, -32768, 32767).astype(np.int16)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    print(f"Wrote audio: {out_wav} ({len(pcm) / sample_rate:.1f}s @ {sample_rate}Hz, downmixed from {num_channels}ch)")


def extract_frames(provider: "data_provider.VrsDataProvider", frames_dir: Path) -> None:
    stream_id = provider.get_stream_id_from_label(RGB_CAMERA_LABEL)
    if stream_id is None:
        raise RuntimeError("No RGB camera stream found in this VRS.")

    frames_dir.mkdir(parents=True, exist_ok=True)
    num_data = provider.get_num_data(stream_id)

    last_saved_s = -FRAME_SAMPLE_INTERVAL_S
    saved = 0
    for i in range(num_data):
        image_data, record = provider.get_image_data_by_index(stream_id, i)
        t_s = record.capture_timestamp_ns / 1e9
        if t_s - last_saved_s < FRAME_SAMPLE_INTERVAL_S:
            continue
        last_saved_s = t_s
        img = Image.fromarray(image_data.to_numpy_array())
        out_path = frames_dir / f"frame_{t_s:09.3f}.jpg"
        img.save(out_path, quality=90)
        saved += 1
    print(f"Wrote {saved} sampled frames to {frames_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    args = parser.parse_args()

    paths = SessionPaths(args.session_id)
    paths.ensure_dirs()

    vrs_path = paths.vrs_file()
    print(f"Loading {vrs_path} ...")
    provider = data_provider.create_vrs_data_provider(str(vrs_path))
    if provider is None:
        raise RuntimeError(f"Failed to open VRS file: {vrs_path}")

    extract_audio(provider, paths.derived_dir / "audio.wav")
    extract_frames(provider, paths.frames_dir)


if __name__ == "__main__":
    main()
