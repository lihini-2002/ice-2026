/**
 * Wires getUserMedia camera feed -> perception -> stepTracker -> comparator
 * -> commandGenerator -> overlay + audio, plus the session-select screen and
 * telemetry posting. This is the browser-native equivalent of
 * learning_runtime/run_offline_test.py's loop — same
 * CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE debounce for step advancement,
 * same component wiring, but driven by a live camera instead of a video
 * file, and throttled explicitly rather than running inference on every
 * requestAnimationFrame tick.
 */

import { AudioDelivery } from "./audio.js";
import { Comparator, ComparisonState } from "./comparator.js";
import { CommandGenerator } from "./commandGenerator.js";
import { HeuristicBrightRegionDetector } from "./heuristicDetector.js";
import { Canvas2DOverlay } from "./overlay.js";
import { MediaPipeHandTracker, Perception } from "./perception.js";
import { CraftTemplates } from "./stepTemplates.js";
import { StepTracker } from "./stepTracker.js";

const TARGET_FPS = 7; // within the 5-10fps target — perception runs at most this often, never per rAF tick
const FRAME_INTERVAL_MS = 1000 / TARGET_FPS;
const CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE = 5; // mirrors learning_runtime/run_offline_test.py

function collectVocabulary(templates) {
  const vocab = new Set();
  for (const step of templates.steps) {
    for (const t of step.requiredTools) vocab.add(t);
    for (const targets of Object.values(step.handState)) {
      for (const t of targets) vocab.add(t);
    }
  }
  return [...vocab].sort();
}

async function postTelemetry(sessionId, stepId, timestamp, classification) {
  // Telemetry is best-effort — a dropped log line shouldn't interrupt
  // coaching. no_evidence frames are never posted (not informative for
  // later expanding common_mistakes, same reasoning commandGenerator.js
  // uses to skip generating a command for them).
  try {
    await fetch("/api/telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, step_id: stepId, timestamp, classification }),
    });
  } catch (err) {
    console.warn("telemetry post failed", err);
  }
}

/**
 * Runs the full coaching loop against a live camera feed for one session.
 * Exported (not just called from DOMContentLoaded) so it can also be driven
 * from a test harness or a notebook with a mocked video element/detector.
 */
export async function startSession(sessionId, { videoElement, canvasElement, detector } = {}) {
  const templates = await CraftTemplates.fetch(`/api/sessions/${sessionId}/step_templates`);
  const vocabulary = collectVocabulary(templates);

  // HeuristicBrightRegionDetector is a classical-CV stand-in (bright/
  // low-saturation region = paper), not a trained model — see
  // heuristicDetector.js and webapp/README.md. Pass a real ObjectDetector
  // (TensorFlow.js/ONNX Runtime Web wrapping a fine-tuned/distilled
  // detector) via startSession(id, { detector }) to use one instead.
  const objectDetector = detector ?? new HeuristicBrightRegionDetector();
  const handTracker = await MediaPipeHandTracker.create();
  const perception = new Perception({ detector: objectDetector, vocabulary, handTracker });

  const tracker = new StepTracker(templates);
  const comparator = new Comparator(templates);
  const commander = new CommandGenerator();
  const overlay = new Canvas2DOverlay(canvasElement);
  const audio = new AudioDelivery();

  videoElement.srcObject = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  await videoElement.play();

  let lastLoggedState = null;
  let consecutiveComplete = 0;
  let lastFrameTime = 0;
  let stopped = false;

  async function loop(nowMs) {
    if (stopped) return;
    if (nowMs - lastFrameTime >= FRAME_INTERVAL_MS) {
      lastFrameTime = nowMs;
      const timestampS = nowMs / 1000;

      const frame = await perception.processFrame(videoElement, timestampS);
      tracker.update(frame);
      const activeStep = tracker.activeStep;
      const comparison = comparator.compare(frame, activeStep);

      overlay.draw({
        videoWidth: videoElement.videoWidth,
        videoHeight: videoElement.videoHeight,
        objects: frame.objects,
        stepIndex: activeStep.stepIndex,
        totalSteps: templates.steps.length,
        correctionText: comparison.detail,
      });

      const command = commander.generate(comparison, activeStep);
      if (command) audio.speak(command);

      if (comparison.state !== ComparisonState.NO_EVIDENCE && comparison.state !== lastLoggedState) {
        postTelemetry(sessionId, activeStep.stepIndex, timestampS, comparison.state);
        lastLoggedState = comparison.state;
      }

      if (comparison.state === ComparisonState.STEP_COMPLETE) {
        consecutiveComplete += 1;
        if (consecutiveComplete >= CONSECUTIVE_COMPLETE_FRAMES_TO_ADVANCE) {
          const next = tracker.advanceToNextStep();
          consecutiveComplete = 0;
          if (next) lastLoggedState = null; // force a fresh telemetry post + command on the new step
        }
      } else {
        consecutiveComplete = 0;
      }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  return {
    stop() {
      stopped = true;
      for (const track of videoElement.srcObject?.getTracks() ?? []) track.stop();
    },
  };
}

async function loadSessionList() {
  const resp = await fetch("/api/sessions");
  const sessions = await resp.json();

  const list = document.getElementById("session-list");
  list.innerHTML = "";
  if (sessions.length === 0) {
    list.innerHTML = "<li>No sessions found. Run scripts/generate_step_templates.py on a session first.</li>";
    return;
  }

  for (const s of sessions) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    const ready = s.status === "ready";
    button.textContent = `${s.craft} — ${s.task_description} (${s.status})`;
    button.disabled = !ready;
    button.title = ready ? "" : "This session still needs human review before a learner can use it.";
    button.addEventListener("click", () => {
      document.getElementById("session-select").hidden = true;
      const coaching = document.getElementById("coaching");
      coaching.hidden = false;
      startSession(s.session_id, {
        videoElement: document.getElementById("camera"),
        canvasElement: document.getElementById("overlay"),
      }).catch((err) => {
        console.error(err);
        alert(`Could not start session: ${err.message}`);
      });
    });
    li.appendChild(button);
    list.appendChild(li);
  }
}

if (typeof document !== "undefined") {
  loadSessionList();
}
