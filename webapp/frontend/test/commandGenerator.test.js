/**
 * JS port of learning_runtime/tests/test_command_generator.py: debouncing
 * and the unreviewed/empty command_templates fallback.
 */

import { describe, expect, it, vi } from "vitest";

import { CommandGenerator } from "../src/commandGenerator.js";

describe("CommandGenerator", () => {
  it("debounces a repeated correction within the window", () => {
    const step = {
      stepIndex: 0,
      narration: "Center the clay.",
      requiredTools: ["clay"],
      gazeFocus: null,
      commandTemplates: { correct_tool: ["Pick up the clay."] },
      commandTemplatesReviewed: true,
    };
    let t = 0;
    const generator = new CommandGenerator({ debounceSeconds: 8.0, clock: () => t });
    const comparison = { state: "wrong_tool" };

    const first = generator.generate(comparison, step);
    expect(first).not.toBeNull();
    expect(first.text).toBe("Pick up the clay.");

    t += 2.0; // still within the debounce window
    expect(generator.generate(comparison, step)).toBeNull();

    t += 7.0; // now past 8s total
    expect(generator.generate(comparison, step)).not.toBeNull();
  });

  it("falls back to a generic sentence when unreviewed", () => {
    const step = {
      stepIndex: 0,
      narration: "Center the clay on the wheel.",
      requiredTools: ["clay"],
      gazeFocus: null,
      commandTemplates: { correct_tool: ["This text should never be used."] },
      commandTemplatesReviewed: false, // unreviewed — must not be delivered
    };
    const generator = new CommandGenerator();
    const comparison = { state: "wrong_tool" };

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const command = generator.generate(comparison, step);

    expect(command).not.toBeNull();
    expect(command.text).toContain("Center the clay on the wheel.");
    expect(command.text).not.toContain("This text should never be used.");
    expect(warnSpy).toHaveBeenCalled();

    warnSpy.mockRestore();
  });

  it("produces no command for no_evidence", () => {
    const step = {
      stepIndex: 0,
      narration: "Center the clay.",
      requiredTools: [],
      gazeFocus: null,
      commandTemplates: {},
      commandTemplatesReviewed: false,
    };
    const generator = new CommandGenerator();
    const comparison = { state: "no_evidence" };

    expect(generator.generate(comparison, step)).toBeNull();
  });
});
