/**
 * Rule-based comparator: given the current perception state and the active
 * step template, classify the learner's contact state as on_track /
 * wrong_tool / wrong_hand_state / wrong_sequence / step_complete.
 *
 * Direct port of learning_runtime/comparator.py — deliberately simple and
 * explicit (no black-box model) so a developer can step through why a given
 * frame produced a given classification while debugging against real
 * footage. Same rationale as the Python reference; keep the two in sync by
 * hand if either changes (see webapp/frontend/test/comparator.test.js,
 * which runs against the same fixture shapes as
 * learning_runtime/tests/test_comparator.py).
 */

export const ComparisonState = Object.freeze({
  ON_TRACK: "on_track",
  WRONG_TOOL: "wrong_tool",
  WRONG_HAND_STATE: "wrong_hand_state",
  WRONG_SEQUENCE: "wrong_sequence",
  STEP_COMPLETE: "step_complete",
  NO_EVIDENCE: "no_evidence", // no hand-object contact this frame — not a failure, just no signal
});

export class ComparisonResult {
  constructor({ state, detail, matchedTools = new Set(), missingTools = new Set(), unexpectedTools = new Set() }) {
    this.state = state;
    this.detail = detail;
    this.matchedTools = matchedTools;
    this.missingTools = missingTools;
    this.unexpectedTools = unexpectedTools;
  }
}

/** side -> objectLabel, for hands that are actually touching something.
 * Side-preserving (unlike a flat label set) so wrong_hand_state can tell
 * "right hand touching the rib tool" apart from "left hand touching the rib
 * tool" even though both put "rib_tool" in the contact set. */
function sideContacts(frame) {
  const map = {};
  for (const c of frame.contacts) {
    if (c.objectLabel !== null && c.objectLabel !== undefined) map[c.side] = c.objectLabel;
  }
  return map;
}

function handStateLabels(step) {
  const labels = new Set();
  for (const targets of Object.values(step.handState)) {
    for (const t of targets) labels.add(t);
  }
  return labels;
}

function intersect(a, b) {
  return new Set([...a].filter((x) => b.has(x)));
}

function difference(a, b) {
  return new Set([...a].filter((x) => !b.has(x)));
}

function union(a, b) {
  return new Set([...a, ...b]);
}

export class Comparator {
  constructor(templates) {
    this.templates = templates;
  }

  compare(frame, activeStep) {
    const contacts = sideContacts(frame);
    const contactLabels = new Set(Object.values(contacts));
    if (contactLabels.size === 0) {
      return new ComparisonResult({
        state: ComparisonState.NO_EVIDENCE,
        detail: "No hand-object contact detected this frame.",
      });
    }

    const requiredTools = new Set(activeStep.requiredTools);
    const expected = union(requiredTools, handStateLabels(activeStep));
    const matched = intersect(contactLabels, expected);
    const unexpected = difference(contactLabels, expected);

    if (matched.size === 0) {
      const otherStep = this._bestOtherStepMatch(frame, activeStep);
      if (otherStep !== null) {
        return new ComparisonResult({
          state: ComparisonState.WRONG_SEQUENCE,
          detail:
            `Contact matches step ${otherStep.stepIndex} ` +
            `('${otherStep.narration.slice(0, 60)}') better than the active step ${activeStep.stepIndex}.`,
          unexpectedTools: unexpected,
          missingTools: requiredTools,
        });
      }
      return new ComparisonResult({
        state: ComparisonState.WRONG_TOOL,
        detail: `Contact with ${[...contactLabels].sort()} does not match this step's required tools ${[...requiredTools].sort()}.`,
        missingTools: requiredTools,
        unexpectedTools: unexpected,
      });
    }

    if (requiredTools.size > 0 && intersect(contactLabels, requiredTools).size === 0) {
      return new ComparisonResult({
        state: ComparisonState.WRONG_TOOL,
        detail: `Missing required tool contact: ${[...requiredTools].sort()}.`,
        matchedTools: matched,
        missingTools: difference(requiredTools, contactLabels),
        unexpectedTools: unexpected,
      });
    }

    // Right tool is being touched by *some* hand — now check *which* hand,
    // per side, against handState. This is where "holding the right tool
    // with the wrong hand" gets caught.
    const wrongSideTargets = new Set();
    for (const [side, targets] of Object.entries(activeStep.handState)) {
      if (!targets.includes(contacts[side])) {
        for (const t of targets) wrongSideTargets.add(t);
      }
    }
    if (wrongSideTargets.size > 0) {
      return new ComparisonResult({
        state: ComparisonState.WRONG_HAND_STATE,
        detail: "Tool contact is present, but not the expected hand placement.",
        matchedTools: matched,
        missingTools: wrongSideTargets,
        unexpectedTools: unexpected,
      });
    }

    if ([...requiredTools].every((t) => contactLabels.has(t))) {
      return new ComparisonResult({
        state: ComparisonState.STEP_COMPLETE,
        detail: "All expected tool/hand contacts observed for this step.",
        matchedTools: matched,
      });
    }

    return new ComparisonResult({
      state: ComparisonState.ON_TRACK,
      detail: "Contact matches the active step.",
      matchedTools: matched,
    });
  }

  _bestOtherStepMatch(frame, activeStep) {
    const contactLabels = new Set(Object.values(sideContacts(frame)));
    let bestStep = null;
    let bestScore = 0;
    for (const step of this.templates.steps) {
      if (step.stepIndex === activeStep.stepIndex) continue;
      const expected = union(new Set(step.requiredTools), handStateLabels(step));
      const score = intersect(contactLabels, expected).size;
      if (score > bestScore) {
        bestStep = step;
        bestScore = score;
      }
    }
    return bestStep;
  }
}
