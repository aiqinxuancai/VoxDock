// Waveform audio player (canvas) — decodes audio for peaks, single active player at a time
let activePlayer = null;
let decodeCtx = null;
const PEAK_RES = 1200;

function getCtx() {
  if (!decodeCtx) decodeCtx = new (window.AudioContext || window.webkitAudioContext)();
  return decodeCtx;
}

function computePeaks(buf) {
  const data = buf.getChannelData(0);
  const block = Math.max(1, Math.floor(data.length / PEAK_RES));
  const peaks = new Float32Array(Math.min(PEAK_RES, data.length));
  let max = 0;
  for (let i = 0; i < peaks.length; i++) {
    let m = 0;
    const start = i * block;
    for (let j = 0; j < block; j += 4) {
      const v = Math.abs(data[start + j] || 0);
      if (v > m) m = v;
    }
    peaks[i] = m;
    if (m > max) max = m;
  }
  if (max > 0) for (let i = 0; i < peaks.length; i++) peaks[i] = Math.pow(peaks[i] / max, 0.8);
  return peaks;
}

function fakePeaks(seed = 7) {
  const p = new Float32Array(PEAK_RES);
  for (let i = 0; i < PEAK_RES; i++) {
    const x = Math.sin(i * 0.05 + seed) * 0.5 + Math.sin(i * 0.013 + seed * 2) * 0.3;
    p[i] = 0.15 + Math.abs(x) * 0.25;
  }
  return p;
}

export const WavePlayer = {
  name: 'WavePlayer',
  props: {
    src: String,
    blob: Object,
    height: { type: Number, default: 56 },
    compact: Boolean,
    autoplay: Boolean,
  },
  emits: ['ended', 'error', 'loaded'],
  data: () => ({ playing: false, current: 0, duration: 0, loading: false, hover: -1, real: false }),
  computed: {
    fmtCur() { return this.fmt(this.current); },
    fmtDur() { return this.fmt(this.duration); },
  },
  watch: { src() { this.load(); }, blob() { this.load(); } },
  mounted() {
    const a = (this.audio = new Audio());
    a.preload = 'auto';
    a.addEventListener('loadedmetadata', () => {
      if (isFinite(a.duration)) {
        this.duration = a.duration;
        if (!this.real) this.$emit('loaded', a.duration);
      }
    });
    a.addEventListener('durationchange', () => { if (isFinite(a.duration)) this.duration = a.duration; });
    a.addEventListener('play', () => { this.playing = true; this.loop(); });
    a.addEventListener('pause', () => { this.playing = false; this.draw(); });
    a.addEventListener('ended', () => { this.playing = false; this.current = 0; this.draw(); this.$emit('ended'); });
    a.addEventListener('error', () => { if (a.src) { this.loading = false; this.$emit('error'); } });
    this.ro = new ResizeObserver(() => this.draw());
    this.ro.observe(this.$refs.wrap);
    this.peaks = fakePeaks();
    this.load();
  },
  beforeUnmount() {
    this.audio.pause();
    this.audio.src = '';
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.ro && this.ro.disconnect();
    cancelAnimationFrame(this.raf);
    if (activePlayer === this) activePlayer = null;
  },
  methods: {
    fmt(s) {
      s = Math.max(0, Math.floor(s || 0));
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    },
    async load() {
      this.audio.pause();
      this.current = 0;
      this.duration = 0;
      this.real = false;
      this.peaks = fakePeaks((this.src || '').length);
      if (this.objectUrl) { URL.revokeObjectURL(this.objectUrl); this.objectUrl = null; }
      if (!this.src && !this.blob) { this.draw(); return; }
      this.loading = true;
      this.draw();
      let blob = this.blob;
      if (!blob) {
        try {
          const res = await fetch(this.src, { credentials: 'same-origin' });
          if (!res.ok) throw new Error(String(res.status));
          blob = await res.blob();
        } catch {
          // cross-origin URLs (platform demo links) – stream directly, no waveform
          this.audio.src = this.src;
          this.loading = false;
          this.draw();
          if (this.autoplay) this.play();
          return;
        }
      }
      this.objectUrl = URL.createObjectURL(blob);
      this.audio.src = this.objectUrl;
      try {
        const buf = await getCtx().decodeAudioData(await blob.arrayBuffer());
        this.peaks = computePeaks(buf);
        this.duration = buf.duration;
        this.real = true;
        this.$emit('loaded', buf.duration);
      } catch { /* keep placeholder peaks */ }
      this.loading = false;
      this.draw();
      if (this.autoplay) this.play();
    },
    play() {
      if (activePlayer && activePlayer !== this) activePlayer.pause();
      activePlayer = this;
      this.audio.play().catch(() => {});
    },
    pause() { this.audio.pause(); },
    toggle() { this.playing ? this.pause() : this.play(); },
    loop() {
      cancelAnimationFrame(this.raf);
      const tick = () => {
        this.current = this.audio.currentTime;
        this.draw();
        if (this.playing) this.raf = requestAnimationFrame(tick);
      };
      tick();
    },
    seek(e) {
      const rect = this.$refs.wrap.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      if (this.duration) {
        this.audio.currentTime = ratio * this.duration;
        this.current = this.audio.currentTime;
        if (!this.playing) this.play();
        this.draw();
      }
    },
    onMove(e) {
      const rect = this.$refs.wrap.getBoundingClientRect();
      this.hover = (e.clientX - rect.left) / rect.width;
      this.draw();
    },
    onLeave() { this.hover = -1; this.draw(); },
    draw() {
      const canvas = this.$refs.canvas;
      const wrap = this.$refs.wrap;
      if (!canvas || !wrap) return;
      const dpr = window.devicePixelRatio || 1;
      const w = wrap.clientWidth;
      const h = this.height;
      if (!w) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        canvas.style.height = h + 'px';
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const barW = this.compact ? 2 : 3;
      const gap = this.compact ? 2 : 2;
      const n = Math.max(1, Math.floor(w / (barW + gap)));
      const peaks = this.peaks;
      const progress = this.duration ? this.current / this.duration : 0;
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0, '#a78bfa');
      grad.addColorStop(0.5, '#6366f1');
      grad.addColorStop(1, '#22d3ee');
      const idle = getComputedStyle(document.documentElement).getPropertyValue('--wave-idle').trim() || 'rgba(255,255,255,.2)';
      for (let i = 0; i < n; i++) {
        const from = Math.floor((i / n) * peaks.length);
        const to = Math.max(from + 1, Math.floor(((i + 1) / n) * peaks.length));
        let m = 0;
        for (let j = from; j < to; j++) if (peaks[j] > m) m = peaks[j];
        const bh = Math.max(2, m * (h - 4));
        const x = i * (barW + gap);
        const y = (h - bh) / 2;
        const ratio = i / n;
        ctx.fillStyle = ratio < progress ? grad : (this.hover >= 0 && ratio < this.hover ? 'rgba(139,92,246,.45)' : idle);
        if (this.loading) ctx.globalAlpha = 0.5;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, barW, bh, barW / 2);
        else ctx.rect(x, y, barW, bh);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    },
  },
  template: `
  <div class="wave-player" :class="{ compact }">
    <button class="wave-play" @click="toggle" :disabled="loading && !duration" :title="playing ? '暂停' : '播放'">
      <Icon v-if="loading && !duration" name="loader" class="spin"/>
      <Icon v-else :name="playing ? 'pause' : 'play'"/>
    </button>
    <div class="wave-body">
      <div class="wave-canvas-wrap" ref="wrap" @click="seek" @mousemove="onMove" @mouseleave="onLeave">
        <canvas ref="canvas" :style="{ height: height + 'px' }"></canvas>
      </div>
      <div class="wave-time" v-if="!compact"><span>{{ fmtCur }}</span><span>{{ fmtDur }}</span></div>
    </div>
    <span v-if="compact" class="tiny mono muted" style="min-width:34px;text-align:right">{{ playing ? fmtCur : fmtDur }}</span>
    <slot/>
  </div>`,
};
