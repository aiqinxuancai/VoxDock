// 合成历史
import { store, provider, toast, navigate, play, confirmDialog, loadSystem } from '../store.js';
import { api } from '../api.js';
import { Avatar, ProviderBadge, Empty } from '../components/ui.js';
import { fmtDuration, fmtBytes, fmtTime, timeAgo, copyText, debounce } from '../utils.js';

const SOURCE = { web: '网页', api: 'API', openai: 'OpenAI 兼容' };

export const History = {
  name: 'History',
  components: { Avatar, ProviderBadge, Empty },
  data: () => ({ items: [], total: 0, page: 1, pageSize: 20, q: '', prov: '', loading: false, expanded: {}, playingId: null }),
  computed: {
    store: () => store,
    pages() { return Math.max(1, Math.ceil(this.total / this.pageSize)); },
  },
  watch: {
    q() { this.debounced(); },
    prov() { this.page = 1; this.load(); },
    page() { this.load(); },
  },
  created() { this.debounced = debounce(() => { this.page = 1; this.load(); }, 300); },
  mounted() { this.load(); },
  methods: {
    provider, fmtDuration, fmtBytes, fmtTime, timeAgo,
    source(s) { return SOURCE[s] || s; },
    async load() {
      this.loading = true;
      try {
        const qs = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        if (this.q) qs.set('q', this.q);
        if (this.prov) qs.set('provider', this.prov);
        const res = await api.get(`/api/generations?${qs}`);
        this.items = res.items;
        this.total = res.total;
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.loading = false;
      }
    },
    playItem(g) {
      this.playingId = g.id;
      play({ title: g.voice_name, subtitle: g.text, src: g.audio_url });
    },
    reuse(g) {
      sessionStorage.setItem('voxdock.reuse', JSON.stringify({ voice_pk: g.voice_pk, text: g.text, params: g.params }));
      navigate('/studio', g.voice_pk ? { voice: g.voice_pk } : undefined);
    },
    copy(g) { copyText(g.text); toast.success('已复制文本'); },
    paramSummary(p) {
      return Object.entries(p || {}).filter(([, v]) => v !== '' && v !== null).map(([k, v]) => `${k}=${v}`).join('  ');
    },
    async remove(g) {
      await api.del(`/api/generations/${g.id}`);
      this.items = this.items.filter((x) => x.id !== g.id);
      this.total--;
      loadSystem().catch(() => {});
    },
    async clearAll() {
      const ok = await confirmDialog({ title: '清空历史', message: '将删除全部合成记录及音频文件，此操作不可恢复。', confirmText: '清空', danger: true });
      if (!ok) return;
      const r = await api.del('/api/generations');
      toast.success(`已删除 ${r.deleted} 条记录`);
      this.page = 1;
      this.load();
      loadSystem().catch(() => {});
    },
  },
  template: `
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">合成历史</h1>
        <p class="page-desc">网页与 API 生成的全部音频，可回放、下载或一键复用参数。</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-danger" @click="clearAll" :disabled="!total"><Icon name="trash" size="sm"/>清空历史</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="input-group">
        <Icon name="search" size="sm"/>
        <input class="input" v-model="q" placeholder="搜索文本或音色名">
      </div>
      <div class="segmented">
        <button :class="{ active: !prov }" @click="prov = ''">全部</button>
        <button v-for="p in store.providers" :key="p.name" :class="{ active: prov === p.name }" @click="prov = p.name">{{ p.label }}</button>
      </div>
      <div class="spacer"></div>
      <span class="small muted">共 {{ total }} 条</span>
    </div>
    <div class="card">
      <div v-if="loading && !items.length" style="padding:20px"><div class="skeleton" style="height:200px"></div></div>
      <Empty v-else-if="!items.length" icon="history" title="暂无合成记录" text="在合成工作台生成的音频会出现在这里">
        <button class="btn btn-primary" style="margin-top:6px" @click="navigate('/studio')"><Icon name="wave"/>去合成</button>
      </Empty>
      <div v-else class="list">
        <div class="list-item" v-for="g in items" :key="g.id" style="align-items:flex-start">
          <button class="wave-play" style="width:38px;height:38px;box-shadow:none;margin-top:2px" @click="playItem(g)"><Icon name="play" size="sm"/></button>
          <div style="flex:1;min-width:0">
            <div class="row" style="gap:8px;margin-bottom:3px">
              <span class="bold">{{ g.voice_name || g.voice_id }}</span>
              <ProviderBadge :name="g.provider"/>
              <span class="tag" v-if="g.model">{{ g.model }}</span>
            </div>
            <div class="hist-text" :class="{ expanded: expanded[g.id] }" @click="expanded[g.id] = !expanded[g.id]">{{ g.text }}</div>
            <div class="hist-meta">
              <span :title="fmtTime(g.created_at)"><Icon name="clock" size="sm" style="width:12px;height:12px;vertical-align:-2px"/> {{ timeAgo(g.created_at) }}</span>
              <span>时长 {{ fmtDuration(g.duration_ms) }}</span>
              <span>{{ g.format }} · {{ fmtBytes(g.size_bytes) }}</span>
              <span>耗时 {{ (g.elapsed_ms / 1000).toFixed(1) }}s</span>
              <span class="tag" style="height:18px">{{ source(g.source) }}</span>
              <span class="mono ellipsis" style="max-width:420px" :title="paramSummary(g.params)">{{ paramSummary(g.params) }}</span>
            </div>
          </div>
          <div class="row" style="gap:2px">
            <button class="btn btn-ghost btn-icon btn-sm" title="复用到工作台" @click="reuse(g)"><Icon name="reset" size="sm"/></button>
            <button class="btn btn-ghost btn-icon btn-sm" title="复制文本" @click="copy(g)"><Icon name="copy" size="sm"/></button>
            <a class="btn btn-ghost btn-icon btn-sm" title="下载" :href="g.audio_url + '?download=1'"><Icon name="download" size="sm"/></a>
            <button class="btn btn-ghost btn-icon btn-sm btn-danger" title="删除" @click="remove(g)"><Icon name="trash" size="sm"/></button>
          </div>
        </div>
      </div>
      <div class="pager" v-if="pages > 1">
        <button class="btn btn-sm btn-icon" :disabled="page <= 1" @click="page--"><Icon name="chevron-left" size="sm"/></button>
        <span class="small">{{ page }} / {{ pages }}</span>
        <button class="btn btn-sm btn-icon" :disabled="page >= pages" @click="page++"><Icon name="chevron-right" size="sm"/></button>
      </div>
    </div>
  </div>`,
};
