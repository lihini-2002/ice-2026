"""Stage 3: run open-vocabulary object detection on the sampled RGB frames
to identify tools/materials the artisan is using at each point in time.

Zero-shot (OWLv2) so we're not locked to a fixed label set — pass the craft's
tool/material vocabulary via meta.json (`known_tools`) as detection prompts,
plus a small set of generic fallback prompts.

Usage:
    python scripts/extract_scene_objects.py <session_id>
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image

from common import SessionPaths, load_json, write_json

GENERIC_PROMPTS = ["hand", "tool", "table", "workbench", "material"]
DETECTION_SCORE_THRESHOLD = 0.15


def frame_timestamp(path: Path) -> float:
    m = re.search(r"frame_(\d+\.\d+)\.jpg", path.name)
    if not m:
        raise ValueError(f"Unexpected frame filename: {path.name}")
    return float(m.group(1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    args = parser.parse_args()

    paths = SessionPaths(args.session_id)
    if not paths.frames_dir.exists() or not any(paths.frames_dir.glob("*.jpg")):
        raise FileNotFoundError(f"No frames found in {paths.frames_dir} — run ingest_vrs.py first.")

    meta = load_json(paths.meta) if paths.meta.exists() else {}
    prompts = list(dict.fromkeys(meta.get("known_tools", []) + GENERIC_PROMPTS))
    print(f"Detection prompts: {prompts}")

    import torch
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading OWLv2 on {device} ...")
    processor = Owlv2Processor.from_pretrained("google/owlv2-base-patch16-ensemble")
    model = Owlv2ForObjectDetection.from_pretrained("google/owlv2-base-patch16-ensemble").to(device)
    model.eval()

    results = []
    frame_paths = sorted(paths.frames_dir.glob("*.jpg"), key=frame_timestamp)
    for frame_path in frame_paths:
        image = Image.open(frame_path).convert("RGB")
        inputs = processor(text=[prompts], images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        target_sizes = torch.tensor([image.size[::-1]])
        detections = processor.post_process_grounded_object_detection(
            outputs=outputs, target_sizes=target_sizes, threshold=DETECTION_SCORE_THRESHOLD
        )[0]

        objects = [
            {"label": prompts[label_idx], "score": round(float(score), 3), "box": [round(float(v), 1) for v in box]}
            for score, label_idx, box in zip(detections["scores"], detections["labels"], detections["boxes"])
        ]
        results.append({
            "timestamp_s": frame_timestamp(frame_path),
            "frame": str(frame_path.relative_to(paths.root)),
            "objects": objects,
        })
        if objects:
            print(f"  {frame_path.name}: {[o['label'] for o in objects]}")

    write_json(paths.objects_json, results)
    print(f"Wrote object detections for {len(results)} frames to {paths.objects_json}")


if __name__ == "__main__":
    main()
