/**
 * Web Speech API (speechSynthesis) wrapper for TTS output — no external TTS
 * service. commandGenerator.js already debounces repeated corrections per
 * (step, category); this layer adds priority ordering on top so a
 * higher-priority command (e.g. safety) isn't stuck behind a lower-priority
 * one still queued or speaking, mirroring the priority learning_runtime's
 * design implies for delivery.py: safety > correct_sequence >
 * correct_motion (grouped with correct_tool) > orient/confirm > encourage.
 * Only the four categories explicitly ordered by the spec (safety,
 * correct_sequence, correct_motion, encourage) have a defined relative
 * priority; the rest are placed at reasonable in-between ranks.
 */

const CATEGORY_PRIORITY = {
  safety: 0,
  correct_sequence: 1,
  correct_motion: 2,
  correct_tool: 2,
  orient: 3,
  confirm: 3,
  encourage: 4,
};

export class AudioDelivery {
  constructor({ synth = window.speechSynthesis, minIntervalSeconds = 2.0, clock = () => performance.now() / 1000 } = {}) {
    this.synth = synth;
    this.minIntervalSeconds = minIntervalSeconds;
    this._clock = clock;
    this._lastSpokenAt = -Infinity;
    this._queue = [];
  }

  /** Enqueues a Command ({ category, text, stepIndex }) from
   * commandGenerator.js and attempts to speak immediately if nothing is
   * currently speaking and the minimum interval has elapsed. */
  speak(command) {
    this._queue.push(command);
    this._queue.sort((a, b) => (CATEGORY_PRIORITY[a.category] ?? 5) - (CATEGORY_PRIORITY[b.category] ?? 5));
    this._drain();
  }

  _drain() {
    if (this.synth.speaking) return;
    const now = this._clock();
    if (now - this._lastSpokenAt < this.minIntervalSeconds) return;
    const next = this._queue.shift();
    if (!next) return;

    const utterance = new SpeechSynthesisUtterance(next.text);
    utterance.onend = () => {
      this._lastSpokenAt = this._clock();
      this._drain();
    };
    utterance.onerror = () => {
      this._lastSpokenAt = this._clock();
      this._drain();
    };
    this._lastSpokenAt = this._clock();
    this.synth.speak(utterance);
  }
}
