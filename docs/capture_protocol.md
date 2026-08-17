# Capture Protocol — Recording an Artisan with Aria Glasses

Pilot scope: **one artisan, one craft, one continuous session.**

## Before the session
- Charge the Aria glasses and pair them with the Aria Mobile Companion app (or Aria Studio on desktop).
- Confirm free storage on the glasses for a full-length recording (video + audio + eye tracking + IMU).
- Pick **one complete, self-contained task** to record (e.g. "throwing a pot," "hand-stitching a seam," "sharpening a chisel") — not a whole day of mixed work. Keeps the pilot extraction tractable.
- Brief the artisan on the narration ask below *before* recording starts — don't try to direct them mid-task.

## Narration ask (read this to the artisan)
> "Please talk through what you're doing the whole time, like you're teaching an apprentice standing next to you. Say what you're about to do before you do it, name the tools and materials as you pick them up, and mention anything you're doing carefully or that a beginner would get wrong. When you move to a new step, start the sentence with 'Next, I...' or 'Now I'm going to...' — that phrase is what tells us a new step has started, so try to say it every time even if it feels repetitive."

This narration cue is intentional: it gives the pipeline a free, reliable, fully-local step-boundary signal (see `scripts/fuse_steps.py --segmenter regex`). If the artisan forgets it, `fuse_steps.py` falls back to LLM-based segmentation (`scripts/llm_segment.py`) by default, which sends the transcript *text* (not audio/video) to the Claude API to infer step boundaries — worth knowing before recording proprietary technique, since it's the one point in the pipeline where data leaves the machine.

## During the session
- Start recording, then have the artisan do a short (~10s) intro: state their name, the craft, and the task they're about to perform. This becomes session metadata.
- Record the task start-to-finish in one take where possible. If a break is needed, stop and start a new recording rather than pausing mid-task (simpler to align timestamps).
- Encourage natural pace — don't rush for the camera.

## After the session
1. Export the `.vrs` file from the glasses via Aria Studio (or USB transfer) to a local machine.
2. Name it `<craft>_<artisan_id>_<yyyymmdd>.vrs` and place it in `videos/<session_id>/raw/`.
3. Record session metadata (artisan name/id, craft, date, task description) in `videos/<session_id>/meta.json` — `run_pipeline.py` will read this.
4. **Before submitting to MPS** (Meta's cloud service for eye gaze / hand tracking): confirm with the artisan/organization that uploading this footage to Meta's servers for processing is acceptable. This is a real data-handling decision for proprietary craft technique — do not treat it as a formality.

## Known limits of this pilot protocol
- Step segmentation defaults to the verbal cue (free, deterministic, fully local) with LLM-based segmentation as an automatic fallback when the cue is missing or the regex segmenter is not explicitly requested — see above. The LLM fallback is a per-transcript API call, not a trained step-detection model; validate its output against several sessions before relying on it for anything downstream that assumes precise step boundaries.
- One artisan, one craft only. Scaling to many artisans/crafts is a later phase (this protocol should still work per-session; the multi-session indexing/dedup is not designed yet).
