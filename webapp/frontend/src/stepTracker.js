/**
 * State machine that tracks which step of a craft the learner is likely
 * attempting, given a stream of PerceptionFrame contact events.
 *
 * Direct port of learning_runtime/step_tracker.py — same sliding-window
 * plurality-vote logic, same tie-break-toward-current-step rule. There's no
 * continuous hand-pose/trajectory data on the learner side, only discrete
 * hand-touching-object contact events, so step detection is built around
 * contact-state matching rather than motion-trajectory matching (same
 * rationale as the Python reference).
 */

export const DEFAULT_WINDOW_SIZE = 15; // frames

function contactLabels(frame) {
  const labels = new Set();
  for (const c of frame.contacts) {
    if (c.objectLabel !== null && c.objectLabel !== undefined) labels.add(c.objectLabel);
  }
  return labels;
}

/** How well this frame's contact state matches a step template: a count of
 * requiredTools/handState labels currently in contact. Simple overlap
 * counting, not a learned model — keeps the tracker debuggable against real
 * footage, same rule-based philosophy as comparator.js. */
export function scoreStep(frame, step) {
  const labels = contactLabels(frame);
  let score = 0;
  for (const tool of step.requiredTools) {
    if (labels.has(tool)) score += 1;
  }
  for (const sideTargets of Object.values(step.handState)) {
    for (const tool of sideTargets) {
      if (labels.has(tool)) score += 1;
    }
  }
  return score;
}

/** Sliding-window plurality vote over which step's contact signature best
 * matches each incoming frame. Ties (including "no evidence this frame")
 * favor staying on the currently active step, so a single ambiguous or
 * empty frame doesn't cause flapping. */
export class StepTracker {
  constructor(templates, windowSize = DEFAULT_WINDOW_SIZE) {
    if (!templates.steps || templates.steps.length === 0) {
      throw new Error("CraftTemplates has no steps to track");
    }
    this.templates = templates;
    this.windowSize = windowSize;
    this._window = []; // fixed-capacity queue, oldest at index 0
    this._activeStepIndex = templates.steps[0].stepIndex;
  }

  get activeStep() {
    return this.templates.steps.find((s) => s.stepIndex === this._activeStepIndex);
  }

  _bestMatchingStep(frame) {
    const scores = this.templates.steps.map((s) => [s.stepIndex, scoreStep(frame, s)]);
    const bestScore = Math.max(...scores.map(([, sc]) => sc));
    if (bestScore === 0) return null; // no contact evidence this frame — abstain from voting
    const candidates = scores.filter(([, sc]) => sc === bestScore).map(([idx]) => idx);
    if (candidates.includes(this._activeStepIndex)) return this._activeStepIndex;
    return Math.min(...candidates);
  }

  update(frame) {
    this._window.push(this._bestMatchingStep(frame));
    if (this._window.length > this.windowSize) this._window.shift();

    const votes = new Map();
    for (const v of this._window) {
      if (v !== null) votes.set(v, (votes.get(v) ?? 0) + 1);
    }
    if (votes.size > 0) {
      const topCount = Math.max(...votes.values());
      const leaders = [...votes.entries()].filter(([, c]) => c === topCount).map(([idx]) => idx);
      if (!leaders.includes(this._activeStepIndex)) {
        this._activeStepIndex = Math.min(...leaders);
      }
    }
    return { activeStepIndex: this._activeStepIndex, votes };
  }

  /** Explicitly move to the next step in sequence (e.g. called by main.js
   * after comparator.js reports step_complete for a few consecutive
   * frames). Returns null and leaves state unchanged if already on the last
   * step. Clears the vote window so the new step isn't immediately
   * overridden by stale votes for the old one. */
  advanceToNextStep() {
    const indices = this.templates.steps.map((s) => s.stepIndex).sort((a, b) => a - b);
    const pos = indices.indexOf(this._activeStepIndex);
    if (pos + 1 >= indices.length) return null;
    this._activeStepIndex = indices[pos + 1];
    this._window = [];
    return this.activeStep;
  }
}
