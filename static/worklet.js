// AudioWorklet: downsample mic audio (context rate, e.g. 48 kHz on iOS) to
// 16 kHz mono and convert to 16-bit little-endian PCM. Each process() block
// posts an Int16Array buffer (transferred) to the main thread for streaming.
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // `sampleRate` is the context rate
    this.carry = 0; // fractional read position carried between blocks
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    if (!ch || ch.length === 0) return true;

    const out = [];
    let pos = this.carry;
    while (pos < ch.length) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const s0 = ch[i];
      const s1 = i + 1 < ch.length ? ch[i + 1] : ch[i];
      let s = s0 + (s1 - s0) * frac;
      if (s > 1) s = 1; else if (s < -1) s = -1;
      out.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      pos += this.ratio;
    }
    this.carry = pos - ch.length;

    if (out.length) {
      const pcm = new Int16Array(out);
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
