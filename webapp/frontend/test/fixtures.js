/**
 * Synthetic fixtures shared by the frontend tests — the JS equivalent of
 * learning_runtime/tests/synthetic.py, using the same two-step craft and
 * the same tool/hand-state values, so the JS and Python test suites verify
 * both implementations against equivalent scenarios.
 */

import { HandContact, PerceptionFrame } from "../src/perception.js";

export const STEP_CENTER = {
  stepIndex: 0,
  narration: "Next, I center the clay on the wheel.",
  requiredTools: ["clay"],
  handState: { right: ["clay"] },
  gazeFocus: "clay",
  commandTemplates: {},
  commandTemplatesReviewed: false,
};

export const STEP_OPEN = {
  stepIndex: 1,
  narration: "Now I'm going to open the clay with the rib tool.",
  requiredTools: ["rib_tool"],
  handState: { right: ["rib_tool"] },
  gazeFocus: "clay",
  commandTemplates: {},
  commandTemplatesReviewed: false,
};

export function twoStepTemplates() {
  return { craft: "pottery", taskDescription: "Throw a small bowl", steps: [STEP_CENTER, STEP_OPEN] };
}

/** makeFrame(1.0, { right: "clay", left: null }) -> a frame whose right hand
 * is in contact with "clay" and whose left hand is tracked but touching
 * nothing. */
export function makeFrame(timestampS, sideToLabel) {
  const contacts = Object.entries(sideToLabel).map(
    ([side, label]) => new HandContact(side, label ?? null, label ? 0.01 : 1.0)
  );
  return new PerceptionFrame(timestampS, [], [], contacts);
}
