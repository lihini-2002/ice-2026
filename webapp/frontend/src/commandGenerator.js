/**
 * Command taxonomy + slot-filled templates + debouncing.
 *
 * Direct port of learning_runtime/command_generator.py. Command categories:
 * orient, confirm, correct_tool, correct_motion, correct_sequence,
 * encourage, safety. Templates are pulled from the active step's
 * commandTemplates field, authored offline (see
 * scripts/generate_step_templates.py) and reviewed by a human. If that
 * field is empty or still unreviewed, this falls back to a generic
 * templated sentence built from narration and logs a console warning — it
 * never fails silently, and it never delivers an unreviewed LLM-drafted
 * command as if it were human-approved coaching copy.
 */

// Mirrors scripts/generate_step_templates.py's COMMAND_CATEGORIES (and
// learning_runtime/command_generator.py's copy of the same list). Kept as a
// separate constant, not imported — this module has no dependency on the
// Python pipeline.
export const COMMAND_CATEGORIES = [
  "orient",
  "confirm",
  "correct_tool",
  "correct_motion",
  "correct_sequence",
  "encourage",
  "safety",
];

const STATE_TO_CATEGORY = {
  on_track: "encourage",
  wrong_tool: "correct_tool",
  wrong_hand_state: "correct_motion",
  wrong_sequence: "correct_sequence",
  step_complete: "confirm",
  no_evidence: "orient",
};

const GENERIC_FALLBACKS = {
  orient: (narration) => `Get your hands back on the workbench for this step: ${narration}`,
  confirm: (narration) => `That matches this step — nice work: ${narration}`,
  correct_tool: (narration) => `Try picking up the tool for this step: ${narration}`,
  correct_motion: (narration) => `Adjust your hand placement for this step: ${narration}`,
  correct_sequence: (narration) => `Hold on — that's a different step. The current step is: ${narration}`,
  encourage: (narration) => `Good, keep going: ${narration}`,
  safety: (narration) => `Take care here: ${narration}`,
};

export class CommandGenerator {
  constructor({ debounceSeconds = 8.0, clock = () => performance.now() / 1000 } = {}) {
    this.debounceSeconds = debounceSeconds;
    this._clock = clock;
    this._lastEmitted = new Map(); // `${stepIndex}:${category}` -> last-emitted time
  }

  generate(comparison, step) {
    if (comparison.state === "no_evidence") return null; // nothing actionable to say about silence

    const category = STATE_TO_CATEGORY[comparison.state];
    const key = `${step.stepIndex}:${category}`;
    const now = this._clock();
    const last = this._lastEmitted.get(key);
    if (last !== undefined && now - last < this.debounceSeconds) {
      return null; // same correction for this step was just given — don't repeat every frame
    }

    this._lastEmitted.set(key, now);
    return { category, text: this._selectTemplate(category, step), stepIndex: step.stepIndex };
  }

  _selectTemplate(category, step) {
    const templates = step.commandTemplatesReviewed ? step.commandTemplates?.[category] : null;
    if (templates && templates.length > 0) {
      return templates[0]
        .replaceAll("{narration}", step.narration)
        .replaceAll("{required_tools}", (step.requiredTools ?? []).join(", "))
        .replaceAll("{gaze_focus}", step.gazeFocus ?? "");
    }
    console.warn(
      `step ${step.stepIndex}: command_templates missing or unreviewed for category '${category}' — ` +
        "falling back to a generic narration-based sentence instead of failing silently"
    );
    return GENERIC_FALLBACKS[category](step.narration);
  }
}
