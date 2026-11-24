// 音色库
import { store, provider, toast, navigate, play, confirmDialog, upsertVoice, removeVoice, loadVoices, loadSystem } from '../store.js';
import { api } from '../api.js';
import { Avatar, StatusPill, ProviderBadge, Empty, Dropdown } from '../components/ui.js';
import { CloneDialog } from './CloneDialog.js';
import { EditVoiceDialog, AddVoiceDialog } from './VoiceDialogs.js';
import { copyText, timeAgo, fmtNumber } from '../utils.js';

export const Voices = {
  name: 'Voices',
  components: { Avatar, StatusPill, ProviderBadge, Empty, Dropdown, CloneDialog, EditVoiceDialog, AddVoiceDialog },
  data: () => ({
    q: '',
    tab: '',
    status: '',
    favOnly: false,
    cloneOpen: false,
    addOpen: false,
    editing: null,
    syncing: '',
    previewing: null,
  }),
  computed: {
    store: () => store,
    filtered() {
      const q = this.q.trim().toLowerCase();
      return store.voices.filter((v) =>
        (!this.tab || v.provider === this.tab) &&
        (!this.status || v.status === this.status) &&
        (!this.favOnly || v.favorite) &&
        (!q || [v.name, v.voice_id, v.description, ...(v.tags || [])].some((s) => (s || '').toLowerCase().includes(q))));
    },
    counts() {
      const c = { total: store.voices.length, ready: 0, training: 0 };
      for (const v of store.voices) { if (v.status === 'ready') c.ready++; if (v.status === 'training') c.training++; }
      return c;
    },
    syncable() { return store.providers.filter((p) => p.configured && p.capabilities.list); },
  },
  watch: {
    'counts.training': {
      immediate: true,
      handler(n) {
        clearInterval(this.poll);
        if (n > 0) this.poll = setInterval(() => loadVoices().catch(() => {}), 6000);
      },
    },
  },
  mounted() {
    if (store.route.query.clone) { this.cloneOpen = true; history.replaceState(null, '', '#/voices'); }
    loadVoices().catch(() => {});
  },
  beforeUnmount() { clearInterval(this.poll); },
  methods: {
    provider, timeAgo, fmtNumber, navigate,
    countOf(name) { return store.voices.filter((v) => v.provider === name).length; },
    async toggleFav(v) {
      const nv = await api.patch(`/api/voices/${v.id}`, { favorite: !v.favorite });
      upsertVoice(nv);
    },
    async refresh(v) {
      try {
        const nv = await api.post(`/api/voices/${v.id}/refresh`);
        upsertVoice(nv);
        toast.success(`状态：${{ ready: '可用', training: '训练中', failed: '失败' }[nv.status] || '未知'}${nv.status_message ? '（' + nv.status_message + '）' : ''}`);
      } catch (e) { toast.error(e.message); }
    },
    async preview(v) {
      if (v.has_demo) return play({ title: v.name, subtitle: '平台试听音频', src: `/api/voices/${v.id}/demo` });
      this.previewing = v.id;
      try {
        const p = provider(v.provider);
        const { blob } = await api.blob('POST', '/api/tts', { voice: v.id, text: p.default_demo_text, output: 'audio', save: false });
        play({ title: v.name, subtitle: p.default_demo_text, blob });
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.previewing = null;
      }
    },
    playSample(v) { play({ title: v.name, subtitle: '参考音频', src: `/api/voices/${v.id}/sample` }); },
    copyId(v) { copyText(v.voice_id); toast.success('已复制音色 ID'); },
    async remove(v) {
      const p = provider(v.provider);
      const canRemote = p.capabilities && p.capabilities.delete && v.source !== 'manual';
      const res = await confirmDialog({
        title: '删除音色',
        message: `确定删除音色「${v.name}」吗？本地参考音频与试听文件也会被删除，历史合成记录保留。`,
        confirmText: '删除',
        danger: true,
        checkbox: canRemote ? `同时删除 ${p.label} 平台上的音色（不可恢复）` : null,
      });
      const ok = typeof res === 'object' ? res.ok : res;
      if (!ok) return;
      const remote = typeof res === 'object' && res.checked;
      try {
        await api.del(`/api/voices/${v.id}?remote=${remote}`);
      } catch (e) {
        const again = await confirmDialog({ title: '平台删除失败', message: `${e.message}\n\n是否仅删除本地记录？`, confirmText: '仅删除本地', danger: true });
        if (!again) return;
        await api.del(`/api/voices/${v.id}?remote=false`);
      }
      removeVoice(v.id);
      toast.success('已删除');
      loadSystem().catch(() => {});
    },
    async sync(p) {
      this.syncing = p.name;
      try {
        const r = await api.post(`/api/providers/${p.name}/sync`);
        await loadVoices();
        toast.success(`${p.label}：新增 ${r.added} 个，更新 ${r.updated} 个音色`);
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.syncing = '';
      }
    },
  },
  template: `
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">音色库</h1>
        <p class="page-desc">管理各平台的克隆音色，支持复刻、同步、试听与一键合成。</p>
      </div>
      <div class="page-actions">
        <Dropdown v-if="syncable.length">
          <template #trigger>
            <button class="btn" :disabled="!!syncing"><Icon :name="syncing ? 'loader' : 'cloud-down'" :class="{ spin: syncing }"/>同步平台音色<Icon name="chevron-down" size="sm"/></button>
          </template>
          <div class="menu-item" v-for="p in syncable" :key="p.name" @click="sync(p)">
            <span class="provider-badge" :style="{ '--c': p.color }"><span class="dot"></span></span>{{ p.label }}
          </div>
        </Dropdown>
        <button class="btn" @click="addOpen = true"><Icon name="plus"/>添加已有音色</button>
        <button class="btn btn-primary" @click="cloneOpen = true"><Icon name="sparkles"/>复刻新音色</button>
      </div>
    </div>

    <div class="stat-row">
      <div class="card stat"><div class="ico"><Icon name="layers"/></div><div><div class="num">{{ counts.total }}</div><div class="lbl">音色总数</div></div></div>
      <div class="card stat"><div class="ico" style="color:var(--success)"><Icon name="check-circle"/></div><div><div class="num">{{ counts.ready }}</div><div class="lbl">可用音色</div></div></div>
      <div class="card stat"><div class="ico" style="color:var(--warning)"><Icon name="clock"/></div><div><div class="num">{{ counts.training }}</div><div class="lbl">训练中</div></div></div>
      <div class="card stat"><div class="ico" style="color:var(--info)"><Icon name="wave"/></div><div><div class="num">{{ fmtNumber(store.system.stats && store.system.stats.generations) }}</div><div class="lbl">累计合成</div></div></div>
    </div>

    <div class="toolbar">
      <div class="input-group">
        <Icon name="search" size="sm"/>
        <input class="input" v-model="q" placeholder="搜索名称 / ID / 标签">
      </div>
      <div class="segmented">
        <button :class="{ active: !tab }" @click="tab = ''">全部 <span class="muted tiny">{{ store.voices.length }}</span></button>
        <button v-for="p in store.providers" :key="p.name" :class="{ active: tab === p.name }" @click="tab = p.name">
          {{ p.label }} <span class="muted tiny">{{ countOf(p.name) }}</span>
        </button>
      </div>
      <select class="select input-sm" style="width:120px" v-model="status">
        <option value="">全部状态</option><option value="ready">可用</option><option value="training">训练中</option>
        <option value="failed">失败</option><option value="unknown">未知</option>
      </select>
      <button class="chip" :class="{ active: favOnly }" @click="favOnly = !favOnly"><Icon name="star" size="sm"/>收藏</button>
    </div>

    <div v-if="!store.voicesLoaded" class="voice-grid">
      <div v-for="i in 6" :key="i" class="skeleton" style="height:190px"></div>
    </div>
    <div v-else-if="!filtered.length" class="card">
      <Empty v-if="store.voices.length" icon="search" title="没有匹配的音色" text="换个关键词或筛选条件试试"/>
      <Empty v-else icon="mic" title="音色库是空的" text="上传或录制 10 秒左右的清晰人声即可复刻专属音色，也可以从平台同步已有音色。">
        <div class="row" style="margin-top:8px">
          <button class="btn btn-primary" @click="cloneOpen = true"><Icon name="sparkles"/>复刻新音色</button>
          <button class="btn" @click="navigate('/providers')"><Icon name="plug"/>配置平台密钥</button>
        </div>
      </Empty>
    </div>
    <div v-else class="voice-grid">
      <div v-for="v in filtered" :key="v.id" class="card voice-card">
        <div class="head">
          <Avatar :name="v.name" :color="provider(v.provider).color"/>
          <div style="flex:1;min-width:0">
            <div class="title ellipsis" :title="v.name">{{ v.name }}</div>
            <div class="meta">
              <ProviderBadge :name="v.provider"/>
              <StatusPill :status="v.status" :title="v.status_message"/>
            </div>
          </div>
          <Icon name="star" class="star" :class="{ on: v.favorite }" @click="toggleFav(v)"/>
        </div>
        <div class="vid" :title="v.voice_id">
          <span>{{ v.voice_id }}</span>
          <button class="btn btn-ghost btn-icon btn-sm" style="width:22px;height:22px" @click="copyId(v)" title="复制"><Icon name="copy" size="sm"/></button>
        </div>
        <div class="row row-wrap" style="gap:6px">
          <span class="tag" v-if="v.model">{{ v.model }}</span>
          <span class="tag" v-for="t in v.tags" :key="t">#{{ t }}</span>
          <span class="tag" v-if="v.source === 'import'">已同步</span>
          <span class="tag" v-if="v.source === 'manual'">手动添加</span>
        </div>
        <div class="desc" v-if="v.description || (v.status !== 'ready' && v.status_message)">
          {{ v.description || v.status_message }}
        </div>
        <div class="tiny muted">使用 {{ v.usage_count || 0 }} 次 · {{ v.last_used_at ? '最近 ' + timeAgo(v.last_used_at) : '创建于 ' + timeAgo(v.created_at) }}</div>
        <div class="actions">
          <button class="btn btn-sm btn-primary" @click="navigate('/studio', { voice: v.id })" :disabled="v.status === 'failed'"><Icon name="wave" size="sm"/>合成</button>
          <button class="btn btn-sm" @click="preview(v)" :disabled="previewing === v.id || v.status === 'failed'" :title="v.has_demo ? '播放平台试听音频' : '快速试听'">
            <Icon :name="previewing === v.id ? 'loader' : 'play'" size="sm" :class="{ spin: previewing === v.id }"/>试听
          </button>
          <Dropdown>
            <template #trigger><button class="btn btn-sm btn-icon"><Icon name="more" size="sm"/></button></template>
            <div class="menu-item" @click="editing = v"><Icon name="edit" size="sm"/>编辑</div>
            <div class="menu-item" @click="refresh(v)"><Icon name="refresh" size="sm"/>刷新状态</div>
            <div class="menu-item" v-if="v.has_sample" @click="playSample(v)"><Icon name="file-audio" size="sm"/>播放参考音频</div>
            <div class="menu-item" @click="copyId(v)"><Icon name="copy" size="sm"/>复制音色 ID</div>
            <div class="menu-sep"></div>
            <div class="menu-item danger" @click="remove(v)"><Icon name="trash" size="sm"/>删除</div>
          </Dropdown>
        </div>
      </div>
    </div>

    <CloneDialog :show="cloneOpen" @close="cloneOpen = false" @done="loadSystem"/>
    <AddVoiceDialog :show="addOpen" @close="addOpen = false"/>
    <EditVoiceDialog :voice="editing" @close="editing = null"/>
  </div>`,
};
