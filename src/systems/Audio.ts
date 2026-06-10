/**
 * Procedural Web Audio. No audio files: every sound is synthesized
 * (oscillators, filtered noise, slow LFO pad). Gain graph:
 *   sources -> sfxGain / musicGain -> masterGain -> destination
 * The three gains are wired straight to the settings sliders.
 */

export class AudioSystem {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private sfx: GainNode | null = null;
  private music: GainNode | null = null;
  private padNodes: OscillatorNode[] = [];
  private padLfo: OscillatorNode | null = null;
  private volumes = { master: 0.8, sfx: 0.8, music: 0.5 };

  /** Create the context on first user gesture (browser autoplay policy). */
  ensure(): boolean {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') void this.ctx.resume();
      return true;
    }
    const Ctor = window.AudioContext;
    if (!Ctor) return false;
    this.ctx = new Ctor();
    this.master = this.ctx.createGain();
    this.sfx = this.ctx.createGain();
    this.music = this.ctx.createGain();
    this.sfx.connect(this.master);
    this.music.connect(this.master);
    this.master.connect(this.ctx.destination);
    this.applyVolumes();
    this.startAmbientPad();
    return true;
  }

  get isRunning(): boolean {
    return this.ctx !== null && this.ctx.state === 'running';
  }

  setVolumes(master: number, sfx: number, music: number): void {
    this.volumes = { master, sfx, music };
    this.applyVolumes();
  }

  private applyVolumes(): void {
    if (!this.ctx || !this.master || !this.sfx || !this.music) return;
    const t = this.ctx.currentTime;
    this.master.gain.setTargetAtTime(this.volumes.master, t, 0.05);
    this.sfx.gain.setTargetAtTime(this.volumes.sfx, t, 0.05);
    this.music.gain.setTargetAtTime(this.volumes.music * 0.25, t, 0.05);
  }

  /** Short UI/interact blip. */
  blip(freq = 880, duration = 0.08, type: OscillatorType = 'square'): void {
    if (!this.ctx || !this.sfx) return;
    const t = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    osc.frequency.exponentialRampToValueAtTime(freq * 1.5, t + duration);
    g.gain.setValueAtTime(0.12, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    osc.connect(g).connect(this.sfx);
    osc.start(t);
    osc.stop(t + duration + 0.02);
  }

  /** Low mechanical hum, e.g. standing near a pedestal. */
  hum(freq = 70, duration = 0.4): void {
    if (!this.ctx || !this.sfx) return;
    const t = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.08, t + duration * 0.3);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    osc.connect(g).connect(this.sfx);
    osc.start(t);
    osc.stop(t + duration + 0.02);
  }

  /** Soft footstep tick. */
  step(): void {
    this.blip(140 + Math.random() * 30, 0.04, 'triangle');
  }

  /**
   * Endless ambient pad: two detuned triangle oscillators through a
   * lowpass whose cutoff is swept by a very slow LFO.
   */
  private startAmbientPad(): void {
    if (!this.ctx || !this.music) return;
    const filter = this.ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 420;
    filter.Q.value = 1.2;
    filter.connect(this.music);

    for (const freq of [110, 110 * 1.498, 220.6]) {
      const osc = this.ctx.createOscillator();
      osc.type = 'triangle';
      osc.frequency.value = freq;
      osc.detune.value = (Math.random() - 0.5) * 12;
      osc.connect(filter);
      osc.start();
      this.padNodes.push(osc);
    }

    this.padLfo = this.ctx.createOscillator();
    this.padLfo.frequency.value = 0.05;
    const lfoGain = this.ctx.createGain();
    lfoGain.gain.value = 260;
    this.padLfo.connect(lfoGain).connect(filter.frequency);
    this.padLfo.start();
  }
}
