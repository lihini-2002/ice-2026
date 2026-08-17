"""Per-frame perception: object detection + hand tracking + hand-to-object
contact inference, for a top-mounted RGB camera on the learner side.

There is no gaze or hand-tracking hardware on the learner side, and no
continuous hand-pose/trajectory stream — only what a webcam-style RGB frame
plus MediaPipe Hands and an object detector can give per frame. Everything
downstream (step_tracker.py, comparator.py) is built around discrete
hand-touching-object contact events, not motion trajectories.

The object detector is a swappable interface (ObjectDetector) so the offline
pipeline's OWLv2 vocabulary (see scripts/extract_scene_objects.py) can be
served by a lighter fine-tuned/distilled model at inference time without
touching any other module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass
class DetectedObject:
    label: str
    score: float
    box: BoundingBox


@dataclass
class HandLandmarks:
    side: str  # "left" | "right"
    points: list[tuple[float, float]]  # 21 (x, y) landmarks, image-normalized [0, 1]
    score: float

    @property
    def palm_center(self) -> tuple[float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (sum(xs) / len(xs), sum(ys) / len(ys))


@dataclass
class HandContact:
    side: str
    object_label: str | None  # None if no object is within CONTACT_DISTANCE_THRESHOLD
    distance: float  # normalized image-space distance to the nearest object's box center


@dataclass
class PerceptionFrame:
    timestamp_s: float
    objects: list[DetectedObject] = field(default_factory=list)
    hands: list[HandLandmarks] = field(default_factory=list)
    contacts: list[HandContact] = field(default_factory=list)


class ObjectDetector(Protocol):
    """Interface a real-time detector implements. Swap in for the offline
    pipeline's OWLv2 model — same open-vocabulary prompting, different
    (lighter) weights suited to real-time inference."""

    def detect(self, frame, vocabulary: list[str]) -> list[DetectedObject]: ...


class StubObjectDetector:
    """No-op placeholder so Perception can be constructed and unit-tested
    without a model loaded. Raises if actually asked to detect — inject a
    real ObjectDetector before running against live or recorded video."""

    def detect(self, frame, vocabulary: list[str]) -> list[DetectedObject]:
        raise NotImplementedError(
            "StubObjectDetector has no model loaded. Inject a real ObjectDetector "
            "(e.g. a distilled/fine-tuned OWLv2 checkpoint) via Perception(detector=...)."
        )


# Normalized image-space distance (palm center to object box center) below
# which a hand counts as "touching/holding" that object. Tune against real
# footage — this is deliberately a simple, debuggable threshold rather than a
# learned contact model, matching comparator.py's philosophy.
CONTACT_DISTANCE_THRESHOLD = 0.08


def infer_contacts(hands: list[HandLandmarks], objects: list[DetectedObject]) -> list[HandContact]:
    """Nearest-object-within-threshold contact inference. One contact record
    per detected hand (object_label is None, not omitted, when nothing is
    close enough — callers can distinguish "hand present, touching nothing"
    from "no hand detected this frame" by checking `hands`)."""
    contacts = []
    for hand in hands:
        hx, hy = hand.palm_center
        best_label, best_dist = None, None
        for obj in objects:
            ox, oy = obj.box.center
            dist = ((hx - ox) ** 2 + (hy - oy) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_label, best_dist = obj.label, dist
        if best_dist is not None and best_dist <= CONTACT_DISTANCE_THRESHOLD:
            contacts.append(HandContact(side=hand.side, object_label=best_label, distance=best_dist))
        else:
            contacts.append(HandContact(side=hand.side, object_label=None, distance=best_dist if best_dist is not None else float("inf")))
    return contacts


class MediaPipeHandTracker:
    """Thin wrapper around MediaPipe Hands. Import is deferred to __init__ so
    this module (and Perception/StubObjectDetector) can be imported — and
    step_tracker/comparator unit-tested — without mediapipe installed."""

    def __init__(self, max_num_hands: int = 2, min_detection_confidence: float = 0.5):
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise ImportError(
                "mediapipe is required for MediaPipeHandTracker — "
                "pip install -r learning_runtime/requirements.txt"
            ) from exc
        self._mp_hands = mp.solutions.hands
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
        )

    def process(self, frame_rgb) -> list[HandLandmarks]:
        result = self._hands.process(frame_rgb)
        hands: list[HandLandmarks] = []
        if not result.multi_hand_landmarks:
            return hands
        for landmarks, handedness in zip(result.multi_hand_landmarks, result.multi_handedness or []):
            classification = handedness.classification[0]
            side = "left" if classification.label.lower() == "left" else "right"
            points = [(lm.x, lm.y) for lm in landmarks.landmark]
            hands.append(HandLandmarks(side=side, points=points, score=classification.score))
        return hands


class Perception:
    """Wires an ObjectDetector + hand tracker into per-frame PerceptionFrame
    output, including hand-to-object contact inference."""

    def __init__(self, detector: ObjectDetector, vocabulary: list[str], hand_tracker: "MediaPipeHandTracker | None" = None):
        self.detector = detector
        self.vocabulary = vocabulary
        self.hand_tracker = hand_tracker or MediaPipeHandTracker()

    def process_frame(self, frame_rgb, timestamp_s: float) -> PerceptionFrame:
        objects = self.detector.detect(frame_rgb, self.vocabulary)
        hands = self.hand_tracker.process(frame_rgb)
        contacts = infer_contacts(hands, objects)
        return PerceptionFrame(timestamp_s=timestamp_s, objects=objects, hands=hands, contacts=contacts)
