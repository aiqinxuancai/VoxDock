// 合成工作台
import { store, provider, toast, navigate, play, upsertVoice, loadSystem } from '../store.js';
import { api } from '../api.js';
import { Avatar, StatusPill, ProviderBadge, Empty } from '../components/ui.js';
import { WavePlayer } from '../components/WavePlayer.js';
import { ParamPanel } from '../components/ParamPanel.js';
import { VoicePicker } from '../components/VoicePicker.js';
import { SAMPLE_TEXTS, defaultsFor, fmtDuration, fmtBytes, timeAgo, copyText } from '../utils.js';

export const Studio = {
  name: 'Studio',
  components: { Avatar, StatusPill, ProviderBadge, Empty, WavePlayer, ParamPanel, VoicePicker },
  data: () => ({
    voiceId: null,
    text: localStorage.getItem('voxdock.draft') || '',
    params: {},
    generating: false,
    result: null,
    error: '',
    recent: [],
    pickerOpen: false,
    samples: SAMPLE_TEXTS,
  }),
  computed: {
    store: () => store,
    voice() { return store.voices.find((v) => v.id === this.voiceId) || null; },
    prov() { return this.voice ? provider(this.voice.provider) : null; },
    limit() { return this.prov ? this.prov.max_text_length : 5000; },
    over() { return this.text.length > this.limit; },
    canGenerate() { return this.voice && this.text.trim() && !this.over && !this.generating && this.voice.status !== 'failed'; },
    providerDefaults() { return this.prov ? defaultsFor(this.prov.tts_params, this.voice.model) : {}; },
    dirtyDefaults() {
      if (!this.voice) return false;
      return JSON.stringify(this.diffParams()) !== JSON.stringify(this.voice.default_params || {});
    },
    apiSnippet() {
      if (!this.voice) return '';
      const body = { voice: this.voice.id, text: this.text.slice(0, 40) || '你好，世界', params: this.diffParams() };
      if (!Object.keys(body.params).length) delete body.params;
      return `curl -X POST ${location.origin}/api/tts \\\n  -H "Authorization: Bearer $VOXDOCK_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(body)}' \\\n  -o output.${this.params.format || 'mp3'}`;
    },
  },
  watch: {
    voiceId(id) {
      if (id) localStorage.setItem('voxdock.voice', id);
      this.resetParams();
      this.loadRecent();
    },
    text(t) { localStorage.setItem('voxdock.draft', t); },
    'store.voices'() { if (!this.voice) this.pickInitial(); },
  },
  mounted() {
    this.pickInitial();
    document.addEventListener('keydown', this.onKey);
  },
  beforeUnmount() { document.removeEventListener('keydown', this.onKey); },
  methods: {
    provider, fmtDuration, fmtBytes, timeAgo, navigate,
    pickInitial() {
      const reuse = sessionStorage.getItem('voxdock.reuse');
      const q = store.route.query.voice;
      let id = q ? Number(q) : Number(localStorage.getItem('voxdock.voice'));
      if (reuse) {
        try {
          const r = JSON.parse(reuse);
          if (r.voice_pk) id = r.voice_pk;
          this.text = r.text || this.text;
          this.pendingParams = r.params;
        } catch { /* ignore */ }
        sessionStorage.removeItem('voxdock.reuse');
      }
      let v = store.voices.find((x) => x.id === id);
      if (!v) v = store.voices.find((x) => x.status === 'ready') || store.voices[0];
      if (v) {
        if (this.voiceId === v.id) this.resetParams();
        this.voiceId = v.id;
      }
    },
    resetParams(force) {
      if (!this.voice) { this.params = {}; return; }
      const base = { ...this.providerDefaults, ...(force ? {} : this.voice.default_params || {}) };
      this.params = this.pendingParams ? { ...base, ...this.pendingParams } : base;
      this.pendingParams = null;
    },
    diffParams() {
      const out = {};
      for (const [k, v] of Object.entries(this.params)) {
        if (v === null || v === '' || v === undefined) continue;
        if (this.providerDefaults[k] !== v) out[k] = v;
      }
      return out;
    },
    onKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); this.generate(); }
    },
    async generate() {
      if (!this.canGenerate) return;
      this.generating = true;
      this.error = '';
      try {
        const res = await api.post('/api/tts', { voice: this.voice.id, text: this.text, params: this.params, output: 'url' });
        this.result = res;
        this.recent.unshift(res.generation);
        this.recent = this.recent.slice(0, 8);
        this.voice.usage_count = (this.voice.usage_count || 0) + 1;
        if (this.voice.status !== 'ready') this.voice.status = 'ready';
        loadSystem().catch(() => {});
      } catch (e) {
        this.error = e.message;
        toast.error(e.message);
      } finally {
        this.generating = false;
      }
    },
    async loadRecent() {
      if (!this.voiceId) return;
      try {
        const res = await api.get(`/api/generations?voice_pk=${this.voiceId}&page_size=8`);
        this.recent = res.items;
      } catch { this.recent = []; }
    },
    async saveDefaults() {
      const v = await api.patch(`/api/voices/${this.voice.id}`, { default_params: this.diffParams() });
      upsertVoice(v);
      toast.success('已保存为该音色的默认参数');
    },
    playGen(g) {
      play({ title: g.voice_name, subtitle: g.text, src: g.audio_url });
    },
    async removeGen(g) {
      await api.del(`/api/generations/${g.id}`);
      this.recent = this.recent.filter((x) => x.id !== g.id);
      if (this.result && this.result.generation && this.result.generation.id === g.id) this.result = null;
    },
    insertSample(s) { this.text = s.text; },
    copyApi() { copyText(this.apiSnippet); toast.success('已复制 curl 命令'); },
    goClone() { navigate('/voices', { clone: 1 }); },
  },
  template: `
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">合成工作台</h1>
        <p class="page-desc">选择克隆音色，输入文本并调节参数，一键生成语音。</p>
      </div>
    </div>

    <div v-if="store.voicesLoaded && !store.voices.length" class="card">
      <Empty icon="mic" title="还没有音色" text="先复刻一个属于你的声音，或从平台同步已有音色。">
        <div class="row" style="margin-top:8px">
          <button class="btn btn-primary" @click="goClone"><Icon name="sparkles"/>复刻新音色</button>
          <button class="btn" @click="navigate('/providers')"><Icon name="plug"/>配置平台</button>
        </div>
      </Empty>
    </div>

    <div v-else class="studio">
      <div class="col" style="gap:16px">
        <div class="card voice-select" @click="pickerOpen = true" v-if="voice">
          <Avatar :name="voice.name" :color="prov.color"/>
          <div style="flex:1;min-width:0">
            <div class="row" style="gap:8px">
              <span class="bold" style="font-size:16px">{{ voice.name }}</span>
              <StatusPill :status="voice.status" :title="voice.status_message"/>
            </div>
            <div class="row small" style="gap:10px;margin-top:3px">
              <ProviderBadge :name="voice.provider"/>
              <span class="tag" v-if="voice.model">{{ voice.model }}</span>
              <span class="muted mono tiny ellipsis">{{ voice.voice_id }}</span>
            </div>
          </div>
          <button class="btn btn-sm"><Icon name="refresh" size="sm"/>更换音色</button>
        </div>
        <div class="card voice-select" v-else @click="pickerOpen = true">
          <div class="avatar" style="--c:#475569">?</div>
          <div class="bold">选择一个音色</div>
        </div>

        <div class="card editor">
          <textarea v-model="text" placeholder="在这里输入想要合成的文本……&#10;&#10;按 Ctrl + Enter 快速生成"></textarea>
          <div class="editor-foot">
            <div class="chips">
              <button v-for="s in samples" :key="s.label" class="chip" @click="insertSample(s)">{{ s.label }}</button>
            </div>
            <div class="actions">
              <span class="counter" :class="{ over }">{{ text.length }} / {{ limit }}</span>
              <button class="btn btn-ghost btn-icon btn-sm" title="清空" @click="text = ''" :disabled="!text"><Icon name="trash" size="sm"/></button>
              <button class="btn btn-primary" :disabled="!canGenerate" @click="generate">
                <Icon :name="generating ? 'loader' : 'sparkles'" :class="{ spin: generating }"/>
                {{ generating ? '合成中…' : '生成语音' }}
                <span class="kbd">Ctrl ↵</span>
              </button>
            </div>
          </div>
        </div>

        <div class="card result-card">
          <div class="row">
            <div class="card-title"><Icon name="waveform" size="sm"/>合成结果</div>
            <div class="spacer"></div>
            <template v-if="result && result.generation && !generating">
              <a class="btn btn-sm" :href="result.audio_url + '?download=1'"><Icon name="download" size="sm"/>下载</a>
            </template>
          </div>
          <div v-if="generating" class="gen-overlay">
            <div class="eq"><span></span><span></span><span></span><span></span><span></span></div>
            <div>
              <div class="bold">正在调用 {{ prov && prov.label }} 合成…</div>
              <div class="small muted">文本 {{ text.length }} 字，通常需要几秒钟</div>
            </div>
          </div>
          <template v-else-if="result">
            <WavePlayer :src="result.audio_url" :height="72" autoplay :key="result.audio_url"/>
            <div class="result-meta">
              <span>时长 <b>{{ fmtDuration(result.duration_ms) }}</b></span>
              <span>耗时 <b>{{ (result.elapsed_ms / 1000).toFixed(2) }}s</b></span>
              <span>格式 <b>{{ result.format }}</b></span>
              <span v-if="result.generation">大小 <b>{{ fmtBytes(result.generation.size_bytes) }}</b></span>
            </div>
          </template>
          <div v-else-if="error" class="alert alert-error"><Icon name="alert" size="sm"/><div>{{ error }}</div></div>
          <div v-else class="placeholder-wave">
            <Icon name="wave" size="xl"/>
            <div class="small">生成的音频会显示在这里</div>
          </div>
        </div>

        <div class="card" v-if="recent.length">
          <div class="card-head">
            <div class="card-title"><Icon name="history" size="sm"/>该音色最近生成</div>
            <div class="spacer"></div>
            <button class="btn btn-ghost btn-sm" @click="navigate('/history')">全部历史<Icon name="chevron-right" size="sm"/></button>
          </div>
          <div class="list">
            <div class="list-item" v-for="g in recent" :key="g.id">
              <button class="btn btn-icon btn-sm" @click="playGen(g)" title="播放"><Icon name="play" size="sm"/></button>
              <div style="flex:1;min-width:0">
                <div class="ellipsis small">{{ g.text }}</div>
                <div class="tiny muted">{{ timeAgo(g.created_at) }} · {{ fmtDuration(g.duration_ms) }} · {{ g.format }}</div>
              </div>
              <button class="btn btn-ghost btn-icon btn-sm" title="复用文本" @click="text = g.text"><Icon name="type" size="sm"/></button>
              <a class="btn btn-ghost btn-icon btn-sm" :href="g.audio_url + '?download=1'" title="下载"><Icon name="download" size="sm"/></a>
              <button class="btn btn-ghost btn-icon btn-sm btn-danger" title="删除" @click="removeGen(g)"><Icon name="trash" size="sm"/></button>
            </div>
          </div>
        </div>
      </div>

      <div class="studio-side">
        <div class="card">
          <div class="card-head">
            <div class="card-title"><Icon name="sliders" size="sm"/>参数调节</div>
            <div class="spacer"></div>
            <button class="btn btn-ghost btn-sm" @click="resetParams(true)" title="恢复平台默认"><Icon name="reset" size="sm"/>重置</button>
          </div>
          <div class="card-body">
            <ParamPanel v-if="prov" :fields="prov.tts_params" :model="voice.model" v-model="params"/>
            <div v-else class="small muted">请先选择音色</div>
          </div>
          <div class="card-body" style="border-top:1px solid var(--border);padding-top:14px" v-if="voice">
            <button class="btn btn-block btn-sm" :disabled="!dirtyDefaults" @click="saveDefaults">
              <Icon name="save" size="sm"/>保存为该音色默认参数
            </button>
          </div>
        </div>
        <div class="card" v-if="voice">
          <div class="card-head">
            <div class="card-title"><Icon name="terminal" size="sm"/>API 调用</div>
            <div class="spacer"></div>
            <button class="btn btn-ghost btn-sm" @click="copyApi"><Icon name="copy" size="sm"/>复制</button>
          </div>
          <div class="card-body">
            <pre class="code" style="font-size:11.5px;white-space:pre-wrap;word-break:break-all">{{ apiSnippet }}</pre>
            <div class="help" style="margin-top:8px">在「API 接入」页面创建 API Key 后即可调用。</div>
          </div>
        </div>
      </div>
    </div>
    <VoicePicker :show="pickerOpen" :current="voiceId" @close="pickerOpen = false" @select="voiceId = $event.id"/>
  </div>`,
};
