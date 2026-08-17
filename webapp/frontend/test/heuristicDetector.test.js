/**
 * Unit tests for the pure pixel-scanning core of heuristicDetector.js —
 * synthetic RGBA buffers, no browser/canvas required, so this runs the same
 * way stepTracker.test.js/comparator.test.js do.
 */

import { describe, expect, it } from "vitest";

import { findBrightRegion } from "../src/heuristicDetector.js";

const WIDTH = 20;
const HEIGHT = 20;

function makeBuffer(width, height, fillColor) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = fillColor[0];
    data[i + 1] = fillColor[1];
    data[i + 2] = fillColor[2];
    data[i + 3] = 255;
  }
  return data;
}

function paintRect(data, width, x0, y0, x1, y1, color) {
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const i = (y * width + x) * 4;
      data[i] = color[0];
      data[i + 1] = color[1];
      data[i + 2] = color[2];
    }
  }
}

describe("findBrightRegion", () => {
  it("finds a bright white square against a dark background", () => {
    const data = makeBuffer(WIDTH, HEIGHT, [20, 20, 20]); // dark background
    paintRect(data, WIDTH, 5, 5, 15, 15, [240, 240, 240]); // bright white square

    const region = findBrightRegion(data, WIDTH, HEIGHT);

    expect(region).not.toBeNull();
    // Normalized box should roughly bound the painted square (5..15 of 20).
    expect(region.x0).toBeCloseTo(5 / WIDTH, 1);
    expect(region.y0).toBeCloseTo(5 / HEIGHT, 1);
    expect(region.x1).toBeCloseTo(15 / WIDTH, 1);
    expect(region.y1).toBeCloseTo(15 / HEIGHT, 1);
  });

  it("returns null when nothing is bright enough", () => {
    const data = makeBuffer(WIDTH, HEIGHT, [30, 30, 30]); // all dark

    expect(findBrightRegion(data, WIDTH, HEIGHT)).toBeNull();
  });

  it("returns null when a bright region is too small to count", () => {
    const data = makeBuffer(WIDTH, HEIGHT, [20, 20, 20]);
    paintRect(data, WIDTH, 9, 9, 10, 10, [240, 240, 240]); // a single bright pixel

    expect(findBrightRegion(data, WIDTH, HEIGHT, { minRegionFraction: 0.02 })).toBeNull();
  });

  it("ignores bright but saturated (colorful) regions", () => {
    const data = makeBuffer(WIDTH, HEIGHT, [20, 20, 20]);
    // Bright magenta: average brightness alone would pass the threshold,
    // but the large per-channel spread means it's not white/gray — should
    // not be mistaken for paper.
    paintRect(data, WIDTH, 5, 5, 15, 15, [255, 20, 255]);

    expect(findBrightRegion(data, WIDTH, HEIGHT)).toBeNull();
  });
});
