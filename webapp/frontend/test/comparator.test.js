/**
 * JS port of learning_runtime/tests/test_comparator.py — covers at least
 * one "wrong tool," one "wrong sequence," and one "on track" case (plus
 * step_complete/wrong_hand_state/no_evidence), against the same fixture
 * shapes as the Python reference.
 */

import { describe, expect, it } from "vitest";

import { Comparator, ComparisonState } from "../src/comparator.js";
import { makeFrame, twoStepTemplates } from "./fixtures.js";

describe("Comparator", () => {
  it("reports on_track for partial contact with a multi-tool step", () => {
    // A step with two required tools, only one of which is in contact —
    // genuinely "on track" (not complete, not wrong).
    const step = {
      stepIndex: 0,
      narration: "Wet the clay and center it.",
      requiredTools: ["clay", "water_bowl"],
      handState: {},
    };
    const templates = { steps: [step] };
    const comparator = new Comparator(templates);

    const frame = makeFrame(0.0, { right: "clay" });
    const result = comparator.compare(frame, step);

    expect(result.state).toBe(ComparisonState.ON_TRACK);
    expect(result.matchedTools.has("clay")).toBe(true);
  });

  it("reports wrong_tool when contact matches no step", () => {
    const templates = twoStepTemplates();
    const activeStep = templates.steps[0]; // requires "clay"
    const comparator = new Comparator(templates);

    const frame = makeFrame(0.0, { right: "sponge" }); // not required by any step
    const result = comparator.compare(frame, activeStep);

    expect(result.state).toBe(ComparisonState.WRONG_TOOL);
    expect(result.missingTools.has("clay")).toBe(true);
  });

  it("reports wrong_sequence when contact matches a different step", () => {
    const templates = twoStepTemplates();
    const activeStep = templates.steps[0]; // requires "clay"
    const comparator = new Comparator(templates);

    // Learner is touching step 1's tool while step 0 is still active.
    const frame = makeFrame(0.0, { right: "rib_tool" });
    const result = comparator.compare(frame, activeStep);

    expect(result.state).toBe(ComparisonState.WRONG_SEQUENCE);
    expect(result.detail).toContain("step 1");
  });

  it("reports step_complete when all expected contacts are present", () => {
    const templates = twoStepTemplates();
    const activeStep = templates.steps[0]; // requiredTools=["clay"], handState={right: ["clay"]}
    const comparator = new Comparator(templates);

    const frame = makeFrame(0.0, { right: "clay" });
    const result = comparator.compare(frame, activeStep);

    expect(result.state).toBe(ComparisonState.STEP_COMPLETE);
  });

  it("reports wrong_hand_state when the right tool is held by the wrong hand", () => {
    const step = {
      stepIndex: 0,
      narration: "Grip the rib tool with your left hand.",
      requiredTools: ["rib_tool"],
      handState: { left: ["rib_tool"] },
    };
    const templates = { steps: [step] };
    const comparator = new Comparator(templates);

    // rib_tool is in contact (satisfies requiredTools) but via the right
    // hand, not the left hand the step calls for.
    const frame = makeFrame(0.0, { right: "rib_tool" });
    const result = comparator.compare(frame, step);

    expect(result.state).toBe(ComparisonState.WRONG_HAND_STATE);
  });

  it("reports no_evidence when no contact is detected", () => {
    const templates = twoStepTemplates();
    const comparator = new Comparator(templates);

    const frame = makeFrame(0.0, { right: null });
    const result = comparator.compare(frame, templates.steps[0]);

    expect(result.state).toBe(ComparisonState.NO_EVIDENCE);
  });
});
