/**
 * Client-side loader for the step_templates.json served by
 * GET /api/sessions/<id>/step_templates. Mirrors
 * learning_runtime/step_templates.py's unwrapping of the offline schema's
 * {"value", "source", "reviewed"} envelope — the runtime only needs the
 * plain values, plus (for command_templates specifically) the `reviewed`
 * flag that commandGenerator.js's fallback logic depends on. See
 * scripts/generate_step_templates.py for why that envelope exists at all.
 */

function unwrap(raw, key, empty) {
  const field = raw[key];
  if (field && typeof field === "object" && "value" in field) {
    return field.value === null || field.value === undefined ? empty : field.value;
  }
  return field === null || field === undefined ? empty : field;
}

function isReviewed(raw, key) {
  const field = raw[key];
  return !!(field && typeof field === "object" && field.reviewed);
}

export class StepTemplate {
  constructor(raw) {
    this.stepIndex = raw.step_index;
    this.narration = raw.narration ?? "";
    this.requiredTools = raw.required_tools ?? [];
    this.handState = raw.hand_state ?? {}; // side -> tool labels
    this.gazeFocus = raw.gaze_focus ?? null;
    this.referenceFrame = raw.reference_frame ?? null;
    this.rationale = unwrap(raw, "rationale", null);
    this.successCriteria = unwrap(raw, "success_criteria", []);
    this.commonMistakes = unwrap(raw, "common_mistakes", []);
    this.commandTemplates = unwrap(raw, "command_templates", {});
    this.commandTemplatesReviewed = isReviewed(raw, "command_templates");
    this.status = raw.status ?? "needs_human_review";
  }
}

export class CraftTemplates {
  constructor({ sessionId, craft, taskDescription, status, steps }) {
    this.sessionId = sessionId;
    this.craft = craft;
    this.taskDescription = taskDescription;
    this.status = status;
    this.steps = steps;
  }

  static fromRaw(raw) {
    const steps = (raw.steps ?? []).map((s) => new StepTemplate(s)).sort((a, b) => a.stepIndex - b.stepIndex);
    return new CraftTemplates({
      sessionId: raw.session_id ?? "",
      craft: raw.craft ?? "",
      taskDescription: raw.task_description ?? "",
      status: raw.status ?? "needs_human_review",
      steps,
    });
  }

  static async fetch(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`Failed to load step templates from ${url}: ${resp.status} ${body}`);
    }
    return CraftTemplates.fromRaw(await resp.json());
  }
}
