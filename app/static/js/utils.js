// Formatting helpers, clipboard, WAV encoding

export function fmtDuration(ms) {
  if (ms == null || isNaN(ms)) return '--:--';
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function fmtSeconds(sec) {
  return fmtDuration((sec || 0) * 1000);
}

export function fmtBytes(n) {
  if (!n && n !== 0) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function fmtNumber(n) {
  if (n == null) return '0';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}

export function timeAgo(iso) {
  if (!iso) return '';
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime();
  const d = (Date.now() - t) / 1000;
  if (d < 45) return '刚刚';
  if (d < 3600) return `${Math.floor(d / 60)} 分钟前`;
  if (d < 86400) return `${Math.floor(d / 3600)} 小时前`;
  if (d < 86400 * 7) return `${Math.floor(d / 86400)} 天前`;
  return new Date(t).toLocaleDateString();
}

export function fmtTime(iso) {
  if (!iso) return '';
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  return t.toLocaleString();
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
}

export function initials(name) {
  const s = (name || '?').trim();
  const m = s.match(/[一-龥]/);
  return m ? m[0] : s.slice(0, 2).toUpperCase();
}

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Merge Float32 chunks, resample linearly and encode 16-bit mono WAV. */
export function encodeWav(chunks, inputRate, outputRate = 24000) {
  const length = chunks.reduce((n, c) => n + c.length, 0);
  const merged = new Float32Array(length);
  let off = 0;
  for (const c of chunks) { merged.set(c, off); off += c.length; }
  let samples = merged;
  if (outputRate && outputRate < inputRate) {
    const ratio = inputRate / outputRate;
    const outLen = Math.floor(merged.length / ratio);
    samples = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), merged.length);
      let sum = 0;
      for (let j = start; j < end; j++) sum += merged[j];
      samples[i] = sum / Math.max(1, end - start);
    }
  } else {
    outputRate = inputRate;
  }
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE');
  w(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, outputRate, true); view.setUint32(28, outputRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  w(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

/** Filter param fields applicable to the given model. */
export function fieldsFor(fields, model) {
  return (fields || []).filter((f) => !f.models || !model || f.models.some((p) => model.startsWith(p)));
}

export function defaultsFor(fields, model) {
  const out = {};
  for (const f of fieldsFor(fields, model)) if (f.default !== undefined && f.default !== null) out[f.key] = f.default;
  return out;
}

export const SAMPLE_TEXTS = [
  { label: '日常问候', text: '你好呀，今天过得怎么样？外面阳光正好，要不要一起出去走走，顺便喝杯咖啡？' },
  { label: '新闻播报', text: '各位观众晚上好，欢迎收看今天的新闻。近日，多项人工智能技术取得突破性进展，语音合成的自然度已接近真人水平。' },
  { label: '故事讲述', text: '很久很久以前，在一座被云雾环绕的山谷里，住着一位会讲故事的老人。每当夜幕降临，孩子们就会围坐在篝火旁，等待新的冒险开始。' },
  { label: '客服应答', text: '您好，很高兴为您服务。您反馈的问题我们已经记录，技术同事会在两小时内与您联系，请您保持电话畅通。' },
  { label: '广告文案', text: '全新一代智能耳机，主动降噪，续航长达四十小时。即刻下单，享受限时八折优惠！' },
  { label: 'English', text: 'Hello there! Welcome to VoxDock, where your voice comes to life in every language you can imagine.' },
];

// Rotating read-aloud scripts so multiple recordings cover more phonemes and tones
export const READ_SCRIPTS = [
  '清晨的阳光透过窗帘洒进房间，我泡了一杯热茶，打开窗户，听见楼下传来自行车的铃声和早点摊的吆喝声。新的一天开始了，我想把今天过得简单而充实：读几页书，散一会儿步，再给远方的朋友打个电话，聊聊最近的生活。',
  '周末的午后，我们沿着河边慢慢地走，柳枝在风里轻轻摇晃，偶尔有几只白鹭从水面掠过。你问我最喜欢哪个季节，我想了想说，大概是秋天吧，天高云淡，空气里都是桂花的香味。',
  '各位朋友大家好，欢迎来到今天的分享。接下来的二十分钟里，我会用三个小故事，聊一聊怎样把复杂的事情讲清楚。准备好了吗？那我们现在就开始吧！',
  '真的吗？这也太让人惊喜了！我本来以为今天只是普通的一天，没想到你们悄悄准备了这么多。谢谢大家，我一定会好好珍惜这份心意。',
];
export const READ_SCRIPT = READ_SCRIPTS[0];

/** Decode any browser-supported audio blob and re-encode it as 24kHz mono 16-bit WAV. */
export async function blobToWav(blob, outputRate = 24000) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  try {
    const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
    const mono = new Float32Array(buf.length);
    for (let ch = 0; ch < buf.numberOfChannels; ch++) {
      const data = buf.getChannelData(ch);
      for (let i = 0; i < data.length; i++) mono[i] += data[i] / buf.numberOfChannels;
    }
    return encodeWav([mono], buf.sampleRate, Math.min(outputRate, buf.sampleRate));
  } finally {
    ctx.close().catch(() => {});
  }
}
