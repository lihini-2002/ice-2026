/**
 * A real, working (if crude) ObjectDetector stand-in for local testing —
 * NOT a trained model. Training/fine-tuning a distilled OWLv2-style
 * detector matching the offline pipeline's vocabulary is explicitly out of
 * scope (see webapp/README.md); this exists so the coaching loop is
 * actually testable against a live camera today rather than throwing on
 * first frame like StubObjectDetector.
 *
 * Detects a bright, low-saturation (white-ish) rectangular region — a
 * reasonable stand-in for "a sheet of A4 paper on a table" given a plain,
 * contrasting background. Classical thresholding, not a neural net, so it
 * needs no model file and runs in a couple of milliseconds even on a
 * low-power laptop. Only fires for a vocabulary term that reads as
 * paper-like (matches /paper|sheet/i) — for any other vocabulary it
 * detects nothing, same as if no object were in view.
 *
 * Swap this out for a real fine-tuned/distilled detector (TensorFlow.js or
 * ONNX Runtime Web) the same way you'd swap out StubObjectDetector — both
 * implement the same ObjectDetector interface from perception.js, so
 * nothing downstream needs to change.
 */

import { BoundingBox, DetectedObject, ObjectDetector } from "./perception.js";

const PAPER_LIKE_RE = /paper|sheet/i;

/**
 * Pure, browser-independent core: scans an RGBA pixel buffer (as produced
 * by CanvasRenderingContext2D.getImageData) for pixels that are bright and
 * low-saturation, and returns the bounding box of all such pixels if they
 * cover enough of the frame to be a real region rather than noise. Kept
 * separate from the DOM-touching detector class so the actual pixel math
 * can be unit-tested with synthetic data, no browser/canvas required — see
 * test/heuristicDetector.test.js.
 *
 * @param {Uint8ClampedArray} data - RGBA bytes, length = width*height*4
 * @returns {{x0:number,y0:number,x1:number,y1:number,coverage:number}|null}
 *   normalized [0,1] box, or null if no sufficiently large region was found
 */
export function findBrightRegion(
  data,
  width,
  height,
  { brightnessThreshold = 170, maxColorSpread = 40, minRegionFraction = 0.02 } = {}
) {
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  let count = 0;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const brightness = (r + g + b) / 3;
      const spread = Math.max(r, g, b) - Math.min(r, g, b);
      if (brightness >= brightnessThreshold && spread <= maxColorSpread) {
        count += 1;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }

  const totalPixels = width * height;
  const coverage = count / totalPixels;
  if (coverage < minRegionFraction) return null;

  return {
    x0: minX / width,
    y0: minY / height,
    x1: (maxX + 1) / width,
    y1: (maxY + 1) / height,
    coverage,
  };
}

export class HeuristicBrightRegionDetector extends ObjectDetector {
  constructor({
    brightnessThreshold = 170,
    maxColorSpread = 40,
    minRegionFraction = 0.02,
    sampleWidth = 96,
    sampleHeight = 72,
  } = {}) {
    super();
    this.options = { brightnessThreshold, maxColorSpread, minRegionFraction };
    this.sampleWidth = sampleWidth;
    this.sampleHeight = sampleHeight;
    this._canvas = null; // created lazily on first detect() — keeps this class constructible outside a browser (e.g. in tests) as long as detect() is never called
    this._ctx = null;
  }

  _ensureCanvas() {
    if (this._canvas) return;
    this._canvas = document.createElement("canvas");
    this._canvas.width = this.sampleWidth;
    this._canvas.height = this.sampleHeight;
    this._ctx = this._canvas.getContext("2d", { willReadFrequently: true });
  }

  async detect(videoElement, vocabulary) {
    const label = vocabulary.find((v) => PAPER_LIKE_RE.test(v));
    if (!label) return []; // nothing in this session's vocabulary is paper-like

    this._ensureCanvas();
    this._ctx.drawImage(videoElement, 0, 0, this.sampleWidth, this.sampleHeight);
    const { data } = this._ctx.getImageData(0, 0, this.sampleWidth, this.sampleHeight);

    const region = findBrightRegion(data, this.sampleWidth, this.sampleHeight, this.options);
    if (!region) return [];

    const box = new BoundingBox(region.x0, region.y0, region.x1, region.y1);
    // Coverage-derived confidence, clamped to 1 — this is a heuristic score,
    // not a calibrated probability.
    const score = Math.min(1, region.coverage / this.options.minRegionFraction / 4);
    return [new DetectedObject(label, score, box)];
  }
}
