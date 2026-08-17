/**
 * Per-frame perception: object detection + hand tracking + hand-to-object
 * contact inference, for a top-mounted RGB webcam on the learner side.
 *
 * This is a direct port of learning_runtime/perception.py — same output
 * shape (PerceptionFrame: objects with boxes, hand landmarks, inferred
 * contacts) so stepTracker.js/comparator.js could be ported mechanically
 * rather than reinvented. The one unavoidable deviation from the Python
 * reference: browser ML inference is asynchronous (model loading, WASM/WebGL
 * backends), so ObjectDetector.detect() and Perception.processFrame() return
 * Promises where the Python versions are synchronous calls.
 *
 * There is no gaze or hand-tracking hardware on the learner side and no
 * continuous hand-pose/trajectory stream — only discrete "hand touching
 * object X" contact events per frame, exactly as in the Python reference.
 */

export class BoundingBox {
  constructor(x0, y0, x1, y1) {
    this.x0 = x0;
    this.y0 = y0;
    this.x1 = x1;
    this.y1 = y1;
  }

  get center() {
    return [(this.x0 + this.x1) / 2, (this.y0 + this.y1) / 2];
  }
}

export class DetectedObject {
  constructor(label, score, box) {
    this.label = label;
    this.score = score;
    this.box = box; // BoundingBox, normalized [0,1] image coordinates
  }
}

export class HandLandmarks {
  constructor(side, points, score) {
    this.side = side; // "left" | "right"
    this.points = points; // Array<[x, y]>, 21 image-normalized landmarks
    this.score = score;
  }

  get palmCenter() {
    const xs = this.points.map((p) => p[0]);
    const ys = this.points.map((p) => p[1]);
    return [xs.reduce((a, b) => a + b, 0) / xs.length, ys.reduce((a, b) => a + b, 0) / ys.length];
  }
}

export class HandContact {
  constructor(side, objectLabel, distance) {
    this.side = side;
    this.objectLabel = objectLabel; // null if nothing is close enough
    this.distance = distance; // normalized image-space distance
  }
}

export class PerceptionFrame {
  constructor(timestampS, objects, hands, contacts) {
    this.timestampS = timestampS;
    this.objects = objects;
    this.hands = hands;
    this.contacts = contacts;
  }
}

/**
 * Interface a real-time detector implements. Swap in for the offline
 * pipeline's OWLv2 model (see scripts/extract_scene_objects.py) — same
 * open-vocabulary prompting, different (lighter) weights suited to
 * real-time inference. Implementations wrap TensorFlow.js or ONNX Runtime
 * Web around a distilled/fine-tuned checkpoint.
 */
export class ObjectDetector {
  // eslint-disable-next-line no-unused-vars
  async detect(frame, vocabulary) {
    throw new Error("ObjectDetector.detect must be implemented by a subclass");
  }
}

/**
 * No-op placeholder so Perception can be constructed and exercised (e.g. in
 * tests, or before a real model is wired in) without a model loaded. Throws
 * if actually asked to detect — inject a real ObjectDetector before running
 * against a live camera. See webapp/README.md for what model file is needed.
 */
export class StubObjectDetector extends ObjectDetector {
  // eslint-disable-next-line no-unused-vars
  async detect(frame, vocabulary) {
    throw new Error(
      "StubObjectDetector has no model loaded. Provide a real ObjectDetector " +
        "(a TensorFlow.js or ONNX Runtime Web wrapper around a distilled/fine-tuned " +
        "OWLv2-style checkpoint) via `new Perception({ detector, ... })` — see webapp/README.md."
    );
  }
}

// Normalized image-space distance (palm center to object box center) below
// which a hand counts as "touching/holding" that object. Same value and
// same rationale as the Python reference — a simple, debuggable threshold
// rather than a learned contact model.
export const CONTACT_DISTANCE_THRESHOLD = 0.08;

/**
 * Nearest-object-within-threshold contact inference. One contact record per
 * detected hand (objectLabel is null, not omitted, when nothing is close
 * enough — callers can distinguish "hand present, touching nothing" from
 * "no hand detected this frame" by checking `hands`). Pure function, direct
 * port of perception.py's infer_contacts.
 */
export function inferContacts(hands, objects) {
  const contacts = [];
  for (const hand of hands) {
    const [hx, hy] = hand.palmCenter;
    let bestLabel = null;
    let bestDist = null;
    for (const obj of objects) {
      const [ox, oy] = obj.box.center;
      const dist = Math.hypot(hx - ox, hy - oy);
      if (bestDist === null || dist < bestDist) {
        bestLabel = obj.label;
        bestDist = dist;
      }
    }
    if (bestDist !== null && bestDist <= CONTACT_DISTANCE_THRESHOLD) {
      contacts.push(new HandContact(hand.side, bestLabel, bestDist));
    } else {
      contacts.push(new HandContact(hand.side, null, bestDist !== null ? bestDist : Infinity));
    }
  }
  return contacts;
}

/**
 * Thin wrapper around MediaPipe Tasks Vision's HandLandmarker. The WASM
 * fileset and the .task model file are loaded from paths you supply (default
 * to a local /mediapipe and /models directory — see webapp/README.md) rather
 * than a CDN, keeping this consistent with the project's offline-first,
 * self-hosted-model philosophy.
 *
 * `@mediapipe/tasks-vision` is imported dynamically inside create() so
 * loading this module doesn't pull the (sizable) WASM loader into the
 * session-select screen's bundle before a session is actually started —
 * mirrors the Python reference deferring `import mediapipe` to __init__.
 */
export class MediaPipeHandTracker {
  static async create({
    wasmBasePath = "/mediapipe/wasm",
    modelAssetPath = "/models/hand_landmarker.task",
    numHands = 2,
    minHandDetectionConfidence = 0.5,
  } = {}) {
    const { HandLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
    const vision = await FilesetResolver.forVisionTasks(wasmBasePath);
    const handLandmarker = await HandLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath, delegate: "GPU" },
      runningMode: "VIDEO",
      numHands,
      minHandDetectionConfidence,
    });
    return new MediaPipeHandTracker(handLandmarker);
  }

  constructor(handLandmarker) {
    this._handLandmarker = handLandmarker;
  }

  /** Synchronous once the model is loaded — matches MediaPipe Tasks
   * Vision's detectForVideo API, and matches the Python reference's
   * synchronous .process(). timestampMs must be monotonically increasing
   * across calls (MediaPipe's VIDEO running-mode requirement). */
  process(videoElement, timestampMs) {
    const result = this._handLandmarker.detectForVideo(videoElement, timestampMs);
    const hands = [];
    const landmarksList = result.landmarks ?? [];
    const handednesses = result.handednesses ?? [];
    for (let i = 0; i < landmarksList.length; i++) {
      const handedness = handednesses[i]?.[0];
      const side = handedness?.categoryName?.toLowerCase() === "left" ? "left" : "right";
      const points = landmarksList[i].map((p) => [p.x, p.y]);
      hands.push(new HandLandmarks(side, points, handedness?.score ?? 0));
    }
    return hands;
  }
}

/** Wires an ObjectDetector + hand tracker into per-frame PerceptionFrame
 * output, including hand-to-object contact inference. */
export class Perception {
  constructor({ detector, vocabulary, handTracker }) {
    this.detector = detector;
    this.vocabulary = vocabulary;
    this.handTracker = handTracker;
  }

  async processFrame(videoElement, timestampS) {
    const objects = await this.detector.detect(videoElement, this.vocabulary);
    const hands = this.handTracker.process(videoElement, timestampS * 1000);
    const contacts = inferContacts(hands, objects);
    return new PerceptionFrame(timestampS, objects, hands, contacts);
  }
}
