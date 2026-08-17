/**
 * JS port of learning_runtime/tests/test_step_tracker.py — same scenarios,
 * against the same fixture shapes, to check the JS port didn't silently
 * diverge from the validated Python reference logic.
 */

import { describe, expect, it } from "vitest";

import { scoreStep, StepTracker } from "../src/stepTracker.js";
import { makeFrame, twoStepTemplates } from "./fixtures.js";

describe("scoreStep", () => {
  it("counts required tool and hand state matches", () => {
    const templates = twoStepTemplates();
    const frame = makeFrame(0.0, { right: "clay" });
    expect(scoreStep(frame, templates.steps[0])).toBe(2); // clay in requiredTools AND handState
    expect(scoreStep(frame, templates.steps[1])).toBe(0);
  });

  it("scores zero with no contact", () => {
    const templates = twoStepTemplates();
    const frame = makeFrame(0.0, { right: null });
    expect(scoreStep(frame, templates.steps[0])).toBe(0);
  });
});

describe("StepTracker", () => {
  it("stays on the initial step while on track", () => {
    const tracker = new StepTracker(twoStepTemplates(), 5);
    let result;
    for (let t = 0; t < 10; t++) result = tracker.update(makeFrame(t, { right: "clay" }));
    expect(result.activeStepIndex).toBe(0);
    expect(tracker.activeStep.stepIndex).toBe(0);
  });

  it("shifts the active step under sustained contact with the next step's tool", () => {
    const tracker = new StepTracker(twoStepTemplates(), 5);
    // A few frames of ambiguous/no contact shouldn't be enough to move.
    for (let t = 0; t < 3; t++) tracker.update(makeFrame(t, { right: null }));
    expect(tracker.activeStep.stepIndex).toBe(0);

    // Sustained contact with step 1's tool should win the sliding-window vote.
    let result;
    for (let t = 3; t < 20; t++) result = tracker.update(makeFrame(t, { right: "rib_tool" }));
    expect(result.activeStepIndex).toBe(1);
    expect(tracker.activeStep.stepIndex).toBe(1);
  });

  it("does not flip on a single ambiguous frame", () => {
    const tracker = new StepTracker(twoStepTemplates(), 5);
    for (let t = 0; t < 5; t++) tracker.update(makeFrame(t, { right: "clay" }));
    expect(tracker.activeStep.stepIndex).toBe(0);

    // One frame touching the other step's tool, surrounded by clay contact,
    // shouldn't be enough to move off the plurality-held step.
    tracker.update(makeFrame(5.0, { right: "rib_tool" }));
    const result = tracker.update(makeFrame(6.0, { right: "clay" }));
    expect(result.activeStepIndex).toBe(0);
  });

  it("advanceToNextStep moves forward and clears the window", () => {
    const tracker = new StepTracker(twoStepTemplates(), 5);
    for (let t = 0; t < 5; t++) tracker.update(makeFrame(t, { right: "clay" }));
    expect(tracker.activeStep.stepIndex).toBe(0);

    const next = tracker.advanceToNextStep();
    expect(next).not.toBeNull();
    expect(next.stepIndex).toBe(1);
    expect(tracker.activeStep.stepIndex).toBe(1);
  });

  it("advanceToNextStep returns null at the last step", () => {
    const tracker = new StepTracker(twoStepTemplates(), 5);
    tracker.advanceToNextStep(); // move to step 1 (the last step)
    expect(tracker.advanceToNextStep()).toBeNull();
    expect(tracker.activeStep.stepIndex).toBe(1);
  });

  it("throws when constructed with no steps", () => {
    expect(() => new StepTracker({ steps: [] })).toThrow();
  });
});
