/**
 * Visual delivery: bounding boxes, step progress, and correction text drawn
 * over the camera feed. Behind a small interface (OverlayRenderer) so a
 * future three.js-based 3D hand-orientation overlay could implement the
 * same `.draw(state)` contract without touching comparator.js/
 * commandGenerator.js — explicitly NOT built in this pass, because
 * step_templates.json only carries discrete contact events (e.g. "holding
 * a4 sheet"), not continuous hand-pose/orientation data. There's nothing
 * for a 3D overlay to visualize yet; see webapp/README.md.
 */

/** @abstract */
export class OverlayRenderer {
  /**
   * @param {{
   *   videoWidth: number, videoHeight: number,
   *   objects: import("./perception.js").DetectedObject[],
   *   stepIndex: number, totalSteps: number, correctionText: string,
   * }} state
   */
  // eslint-disable-next-line no-unused-vars
  draw(state) {
    throw new Error("OverlayRenderer.draw must be implemented by a subclass");
  }
}

export class Canvas2DOverlay extends OverlayRenderer {
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  }

  draw({ videoWidth, videoHeight, objects = [], stepIndex, totalSteps, correctionText = "" }) {
    const { ctx, canvas } = this;
    if (videoWidth && canvas.width !== videoWidth) canvas.width = videoWidth;
    if (videoHeight && canvas.height !== videoHeight) canvas.height = videoHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "#3ddc84";
    ctx.lineWidth = 2;
    ctx.font = "14px sans-serif";
    ctx.fillStyle = "#3ddc84";
    for (const obj of objects) {
      const x = obj.box.x0 * canvas.width;
      const y = obj.box.y0 * canvas.height;
      const w = (obj.box.x1 - obj.box.x0) * canvas.width;
      const h = (obj.box.y1 - obj.box.y0) * canvas.height;
      ctx.strokeRect(x, y, w, h);
      ctx.fillText(obj.label, x + 4, Math.max(12, y - 4));
    }

    this._drawBanner(8, 8, `Step ${stepIndex + 1} of ${totalSteps}`);
    if (correctionText) {
      this._drawBanner(8, canvas.height - 40, correctionText, canvas.width - 16);
    }
  }

  _drawBanner(x, y, text, width = 200) {
    const { ctx } = this;
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
    ctx.fillRect(x, y, width, 32);
    ctx.fillStyle = "#ffffff";
    ctx.font = "14px sans-serif";
    ctx.fillText(text, x + 8, y + 20, width - 16);
  }
}
