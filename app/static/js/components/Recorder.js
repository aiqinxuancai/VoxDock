// In-browser microphone recorder producing 24kHz mono WAV
import { encodeWav, READ_SCRIPT } from '../utils.js';

export const Recorder = {
  name: 'Recorder',
  props: { maxSeconds: { type: Number, default: 120 }, script: { type: String, default: READ_SCRIPT } },
  emits: ['recorded'],
  data: () => ({ state: 'idle', elapsed: 0, levels: Array(28).fill(3), error: '' }),
  computed: {
    time() {
      const s = Math.floor(this.elapsed);
      return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    },
    supported() { return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia); },
  },
  beforeUnmount() { this.cleanup(); },
  methods: {
    async start() {
      this.error = '';
      if (!this.supported) {
        this.error = '当前浏览器环境不支持录音（需 HTTPS 或 localhost 访问）';
        return;
      }
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      } catch (e) {
        this.error = '无法访问麦克风：' + (e.message || e.name);
        return;
      }
      const ctx = (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
      const src = (this.src = ctx.createMediaStreamSource(this.stream));
      const analyser = (this.analyser = ctx.createAnalyser());
      analyser.fftSize = 512;
      const proc = (this.proc = ctx.createScriptProcessor(4096, 1, 1));
      this.chunks = [];
      proc.onaudioprocess = (e) => this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      src.connect(analyser);
      src.connect(proc);
      proc.connect(ctx.destination);
      this.state = 'recording';
      this.startedAt = performance.now();
      const buf = new Uint8Array(analyser.fftSize);
      const tick = () => {
        if (this.state !== 'recording') return;
        this.elapsed = (performance.now() - this.startedAt) / 1000;
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        const rms = Math.sqrt(sum / buf.length);
        this.levels = [...this.levels.slice(1), Math.max(3, Math.min(34, rms * 160))];
        if (this.elapsed >= this.maxSeconds) { this.stop(); return; }
        this.raf = requestAnimationFrame(tick);
      };
      tick();
    },
    stop() {
      if (this.state !== 'recording') return;
      const rate = this.ctx.sampleRate;
      this.cleanup();
      this.state = 'idle';
      if (this.elapsed < 2) {
        this.error = '录音时间太短，请至少录制 5 秒以上';
        return;
      }
      const blob = encodeWav(this.chunks, rate, 24000);
      this.chunks = [];
      this.$emit('recorded', blob, this.script);
    },
    cleanup() {
      cancelAnimationFrame(this.raf);
      try { this.proc && this.proc.disconnect(); this.src && this.src.disconnect(); } catch { /* noop */ }
      this.stream && this.stream.getTracks().forEach((t) => t.stop());
      this.ctx && this.ctx.close().catch(() => {});
      this.proc = this.src = this.stream = this.ctx = null;
    },
    toggle() { this.state === 'recording' ? this.stop() : this.start(); },
  },
  template: `
  <div class="recorder">
    <div class="read-script" v-if="script">
      <div class="tiny muted" style="margin-bottom:4px">请用自然、清晰的语气朗读（建议 10~30 秒，安静环境）：</div>
      {{ script }}
    </div>
    <div class="rec-level"><span v-for="(l, i) in levels" :key="i" :style="{ height: l + 'px', opacity: state === 'recording' ? 1 : .35 }"></span></div>
    <div class="rec-time">{{ time }}</div>
    <button class="rec-btn" :class="{ recording: state === 'recording' }" @click="toggle">
      <Icon :name="state === 'recording' ? 'stop' : 'mic'"/>
    </button>
    <div class="small muted">{{ state === 'recording' ? '点击停止录音' : '点击开始录音' }}</div>
    <div v-if="error" class="alert alert-error" style="width:100%"><Icon name="alert" size="sm"/>{{ error }}</div>
  </div>`,
};
