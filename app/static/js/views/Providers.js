// 平台配置
import { store, toast, loadProviders, loadVoices } from '../store.js';
import { api } from '../api.js';
import { FormField } from '../components/ui.js';

const ProviderPanel = {
  name: 'ProviderPanel',
  components: { FormField },
  props: { p: Object },
  data() {
    return { values: {}, sources: {}, enabled: true, original: {}, loading: true, saving: false, testing: false, syncing: false, showAdv: false, result: null, guideOpen: !this.p.configured };
  },
  computed: {
    basic() { return this.p.credential_fields.filter((f) => f.group !== 'advanced'); },
    advanced() { return this.p.credential_fields.filter((f) => f.group === 'advanced'); },
    dirty() { return JSON.stringify(this.values) !== JSON.stringify(this.original); },
  },
  mounted() { this.load(); },
  methods: {
    async load() {
      this.loading = true;
      try {
        const cfg = await api.get(`/api/providers/${this.p.name}/config`);
        this.sources = cfg.sources;
        this.enabled = cfg.enabled;
        const vals = {};
        for (const f of this.p.credential_fields) vals[f.key] = f.secret ? '' : (cfg.values[f.key] || '');
        this.masked = cfg.values;
        this.values = vals;
        this.original = { ...vals };
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.loading = false;
      }
    },
    placeholder(f) {
      if (f.secret && this.masked && this.masked[f.key]) return `已配置 ${this.masked[f.key]}${this.sources[f.key] === 'env' ? '（环境变量）' : ''}，留空保持不变`;
      return f.placeholder;
    },
    fieldFor(f) { return { ...f, placeholder: this.placeholder(f) }; },
    async save() {
      this.saving = true;
      try {
        const payload = {};
        for (const f of this.p.credential_fields) {
          const v = this.values[f.key];
          if (f.secret) { if (v) payload[f.key] = v; }
          else if (v !== this.original[f.key]) payload[f.key] = v;
        }
        await api.put(`/api/providers/${this.p.name}/config`, { values: payload, enabled: this.enabled });
        await Promise.all([this.load(), loadProviders()]);
        toast.success(`${this.p.label} 配置已保存`);
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.saving = false;
      }
    },
    async clearSecret(f) {
      await api.put(`/api/providers/${this.p.name}/config`, { values: { [f.key]: '' } });
      await Promise.all([this.load(), loadProviders()]);
      toast.success(`已清除 ${f.label}`);
    },
    async toggleEnabled() {
      await api.put(`/api/providers/${this.p.name}/config`, { values: {}, enabled: this.enabled });
      await loadProviders();
    },
    async test() {
      this.testing = true;
      this.result = null;
      try {
        if (this.dirty) await this.save();
        const r = await api.post(`/api/providers/${this.p.name}/test`);
        this.result = { ok: true, message: r.message };
      } catch (e) {
        this.result = { ok: false, message: e.message };
      } finally {
        this.testing = false;
      }
    },
    async sync() {
      this.syncing = true;
      try {
        const r = await api.post(`/api/providers/${this.p.name}/sync`);
        await loadVoices();
        toast.success(`同步完成：新增 ${r.added}，更新 ${r.updated}`);
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.syncing = false;
      }
    },
  },
  template: `
  <div class="card provider-panel" :style="{ '--c': p.color }">
    <div class="ph">
      <div class="logo">{{ p.label.slice(0, 1) }}</div>
      <div style="flex:1;min-width:0;position:relative">
        <div class="row" style="gap:8px">
          <span class="bold" style="font-size:16px">{{ p.label }}</span>
          <span class="badge-soft" :class="p.configured ? 'badge-ok' : 'badge-off'">{{ p.configured ? '已配置' : '未配置' }}</span>
        </div>
        <div class="small muted">{{ p.vendor }}</div>
      </div>
      <label class="switch" title="启用 / 停用" style="position:relative">
        <input type="checkbox" v-model="enabled" @change="toggleEnabled"><span class="track"></span>
      </label>
    </div>
    <div class="card-body">
      <p class="small text-2" style="margin:0 0 14px">{{ p.description }}</p>
      <div v-if="p.guide && p.guide.length" class="guide" :class="{ open: guideOpen }">
        <div class="guide-head" @click="guideOpen = !guideOpen">
          <Icon name="book" size="sm"/>
          <span class="bold">配置指引</span>
          <span class="tiny muted">{{ p.guide.length }} 步完成接入</span>
          <span class="spacer"></span>
          <Icon :name="guideOpen ? 'chevron-down' : 'chevron-right'" size="sm"/>
        </div>
        <ol v-if="guideOpen" class="guide-steps">
          <li v-for="(s, i) in p.guide" :key="i">
            <span class="step-num">{{ i + 1 }}</span>
            <div class="step-body">
              <div class="step-title">{{ s.title }}</div>
              <div class="step-text">{{ s.text }}</div>
              <div class="step-links" v-if="s.links && s.links.length">
                <a v-for="l in s.links" :key="l.url" class="link-chip" :href="l.url" target="_blank" rel="noopener noreferrer" :title="l.url">
                  {{ l.label }}<Icon name="external" size="sm"/>
                </a>
              </div>
            </div>
          </li>
        </ol>
      </div>
      <div v-if="loading" class="skeleton" style="height:120px"></div>
      <template v-else>
        <div v-for="f in basic" :key="f.key" style="margin-bottom:14px">
          <FormField :field="fieldFor(f)" v-model="values[f.key]"/>
          <div class="row tiny" style="margin-top:4px;gap:6px" v-if="sources[f.key] === 'env' || (f.secret && sources[f.key] === 'db')">
            <span class="source-tag" v-if="sources[f.key] === 'env'">来自环境变量</span>
            <a v-if="f.secret && sources[f.key] === 'db'" href="javascript:;" class="muted" @click="clearSecret(f)">清除已保存的值</a>
          </div>
        </div>
        <div v-if="advanced.length" class="param-group-toggle" @click="showAdv = !showAdv" style="margin-bottom:10px">
          <Icon :name="showAdv ? 'chevron-down' : 'chevron-right'" size="sm"/>高级设置
        </div>
        <div v-if="showAdv">
          <div v-for="f in advanced" :key="f.key" style="margin-bottom:14px">
            <FormField :field="fieldFor(f)" v-model="values[f.key]"/>
          </div>
        </div>
        <div v-if="result" class="alert" :class="result.ok ? 'alert-ok' : 'alert-error'" style="margin-bottom:12px">
          <Icon :name="result.ok ? 'check-circle' : 'alert'" size="sm"/><div style="word-break:break-all">{{ result.message }}</div>
        </div>
      </template>
    </div>
    <div class="card-body row row-wrap" style="border-top:1px solid var(--border);padding-top:14px">
      <button class="btn btn-primary btn-sm" :disabled="saving || !dirty" @click="save"><Icon name="save" size="sm"/>保存</button>
      <button class="btn btn-sm" :disabled="testing" @click="test"><Icon :name="testing ? 'loader' : 'zap'" size="sm" :class="{ spin: testing }"/>测试连接</button>
      <button class="btn btn-sm" v-if="p.capabilities.list" :disabled="syncing || !p.configured" @click="sync">
        <Icon :name="syncing ? 'loader' : 'cloud-down'" size="sm" :class="{ spin: syncing }"/>同步音色
      </button>
      <div class="spacer"></div>
      <a class="btn btn-ghost btn-sm" :href="p.docs_url" target="_blank" rel="noopener"><Icon name="book" size="sm"/>文档</a>
      <a class="btn btn-ghost btn-sm" :href="p.console_url" target="_blank" rel="noopener"><Icon name="external" size="sm"/>控制台</a>
    </div>
  </div>`,
};

export const Providers = {
  name: 'Providers',
  components: { ProviderPanel },
  computed: { store: () => store },
  template: `
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">平台配置</h1>
        <p class="page-desc">配置各声音克隆平台的密钥。密钥保存在本地数据库，也可通过环境变量注入。</p>
      </div>
    </div>
    <div class="grid grid-2" style="align-items:start">
      <ProviderPanel v-for="p in store.providers" :key="p.name" :p="p"/>
    </div>
  </div>`,
};
