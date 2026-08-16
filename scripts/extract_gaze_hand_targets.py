"""Stage 3.5: link MPS eye-gaze and hand-tracking samples to the tools/
materials detected by extract_scene_objects.py, by projecting each gaze
point and hand palm position from 3D device space into the RGB camera's
2D image plane and checking which detection box it lands in.

Geometry:
    - Hand landmarks (`landmark_positions_device` / `get_palm_position_device`)
      are already in the "device" frame at their own sample timestamp.
    - Eye gaze points are in the "CPF" (central pupil frame); converted to
      device frame via `device_calibration.get_transform_device_cpf()`.
    - Device -> RGB camera is a fixed physical transform
      (`camera_calib.get_transform_device_camera()`), so any device-frame
      point projects into the RGB image with just that one static transform
      and the camera's intrinsics (`camera_calib.project(...)`), regardless
      of which VRS frame index we're looking at.
    - Detection boxes only exist at the sparse sampled-frame timestamps from
      extract_scene_objects.py, so we associate each gaze/hand sample with
      the nearest sampled frame within MAX_FRAME_TIME_DELTA_S and test
      against that frame's boxes. Scene content can drift a little within
      that window — acceptable for the pilot's step-level aggregation.

Usage:
    python scripts/extract_gaze_hand_targets.py output/<session_id>
"""

from __future__ import annotations

import argparse
import bisect
from pathlib import Path

import numpy as np
from projectaria_tools.core import data_provider, mps

from common import SessionPaths, load_json, write_json

RGB_CAMERA_LABEL = "camera-rgb"
# Half of ingest_vrs.py's FRAME_SAMPLE_INTERVAL_S — a gaze/hand sample more
# than this from the nearest sampled frame has no detection boxes to test.
MAX_FRAME_TIME_DELTA_S = 1.0
# Fallback depth (meters) for gaze points MPS couldn't triangulate — a
# close-range, hands-on-a-workbench assumption.
DEFAULT_GAZE_DEPTH_M = 0.5


def point_in_box(pixel: tuple[float, float], box: list[float]) -> bool:
    x, y = pixel
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def label_for_pixel(pixel, frame_objects: dict | None) -> str | None:
    if pixel is None or frame_objects is None:
        return None
    candidates = [o for o in frame_objects["objects"] if point_in_box(pixel, o["box"])]
    if not candidates:
        return None
    return max(candidates, key=lambda o: o["score"])["label"]


def make_nearest_frame_lookup(objects: list[dict]):
    timestamps = sorted(f["timestamp_s"] for f in objects)
    by_ts = {f["timestamp_s"]: f for f in objects}

    def nearest(t_s: float) -> dict | None:
        idx = bisect.bisect_left(timestamps, t_s)
        best_dt, best_ts = None, None
        for cand in (idx - 1, idx):
            if 0 <= cand < len(timestamps):
                dt = abs(timestamps[cand] - t_s)
                if dt <= MAX_FRAME_TIME_DELTA_S and (best_dt is None or dt < best_dt):
                    best_dt, best_ts = dt, timestamps[cand]
        return by_ts[best_ts] if best_ts is not None else None

    return nearest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()

    paths = SessionPaths(args.session_dir)

    if not paths.objects_json.exists():
        raise FileNotFoundError(f"{paths.objects_json} not found — run extract_scene_objects.py first.")
    objects = load_json(paths.objects_json)
    nearest_frame = make_nearest_frame_lookup(objects)

    mps_paths = mps.MpsDataPathsProvider(str(paths.mps_dir)).get_data_paths()
    if not mps_paths.eyegaze.general_eyegaze and not mps_paths.hand_tracking.hand_tracking_results:
        print(f"No MPS eye-gaze or hand-tracking output found under {paths.mps_dir} — "
              "submit the recording to MPS first (see docs/capture_protocol.md). Skipping.")
        write_json(paths.gaze_hand_json, [])
        return

    vrs_path = paths.vrs_file()
    provider = data_provider.create_vrs_data_provider(str(vrs_path))
    if provider is None:
        raise RuntimeError(f"Failed to open VRS file: {vrs_path}")

    device_calib = provider.get_device_calibration()
    rgb_calib = device_calib.get_camera_calib(RGB_CAMERA_LABEL)
    camera_T_device = rgb_calib.get_transform_device_camera().inverse()
    device_T_cpf = device_calib.get_transform_device_cpf()

    def project_device_point(point_device) -> tuple[float, float] | None:
        point_camera = camera_T_device @ np.asarray(point_device, dtype=np.float64).reshape(3, 1)
        pixel = rgb_calib.project(point_camera)
        if pixel is None:
            return None
        # project() returns a flat [x, y] array, not a (2,1) column.
        return float(pixel[0]), float(pixel[1])

    samples: dict[float, dict] = {}

    if mps_paths.eyegaze.general_eyegaze:
        gaze_list = mps.read_eyegaze(mps_paths.eyegaze.general_eyegaze)
        linked = 0
        for g in gaze_list:
            t_s = g.tracking_timestamp.total_seconds()
            if g.spatial_gaze_point_valid:
                point_cpf = np.asarray(g.spatial_gaze_point_in_cpf, dtype=np.float64).reshape(3, 1)
            else:
                point_cpf = np.asarray(
                    mps.get_eyegaze_point_at_depth(g.yaw, g.pitch, DEFAULT_GAZE_DEPTH_M), dtype=np.float64
                ).reshape(3, 1)
            point_device = device_T_cpf @ point_cpf
            pixel = project_device_point(point_device)
            label = label_for_pixel(pixel, nearest_frame(t_s))
            samples.setdefault(t_s, {})["gaze_target"] = label
            linked += bool(label)
        print(f"Eye gaze: {len(gaze_list)} samples, {linked} linked to a detected object.")
    else:
        print(f"No eye-gaze MPS output found under {paths.mps_dir} — did you request eye gaze from MPS?")

    if mps_paths.hand_tracking.hand_tracking_results:
        hand_list = mps.hand_tracking.read_hand_tracking_results(mps_paths.hand_tracking.hand_tracking_results)
        linked = 0
        for r in hand_list:
            t_s = r.tracking_timestamp.total_seconds()
            entry = samples.setdefault(t_s, {})
            frame = nearest_frame(t_s)
            for side_name, side in (("left", r.left_hand), ("right", r.right_hand)):
                if side is None:
                    continue
                point_device = side.get_palm_position_device()
                pixel = project_device_point(point_device)
                label = label_for_pixel(pixel, frame)
                entry[f"{side_name}_hand_target"] = label
                linked += bool(label)
        print(f"Hand tracking: {len(hand_list)} samples, {linked} hand-target links found.")
    else:
        print(f"No hand-tracking MPS output found under {paths.mps_dir} — did you request hand tracking from MPS?")

    out = [{"timestamp_s": t, **v} for t, v in sorted(samples.items())]
    write_json(paths.gaze_hand_json, out)
    print(f"Wrote {len(out)} gaze/hand target samples to {paths.gaze_hand_json}")


if __name__ == "__main__":
    main()
