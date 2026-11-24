// VoxDock web app entry
import { createApp } from '../vendor/vue.esm-browser.prod.js';
import { store, bootstrap, applyTheme, navigate, loadAuth, toast } from './store.js';
import { api } from './api.js';
import { Icon } from './icons.js';
import { Modal, Toasts, ConfirmHost } from './components/ui.js';
import { WavePlayer } from './components/WavePlayer.js';
import { Studio } from './views/Studio.js';
import { Voices } from './views/Voices.js';
import { History } from './views/History.js';
import { Providers } from './views/Providers.js';
import { ApiDocs } from './views/ApiDocs.js';

const NAV = [
  { path: '/studio', label: '合成工作台', icon: 'wave', view: 'Studio' },
  { path: '/voices', label: '音色库', icon: 'layers', view: 'Voices' },
  { path: '/history', label: '合成历史', icon: 'history', view: 'History' },
  { path: '/providers', label: '平台配置', icon: 'plug', view: 'Providers', section: '设置' },
  { path: '/api', label: 'API 接入', icon: 'code', view: 'ApiDocs' },
];

const Login = {
  name: 'Login',
  data: () => ({ password: '', loading: false, error: '' }),
  methods: {
    async submit() {
      this.loading = true;
      this.error = '';
      try {
        await api.post('/api/auth/login', { password: this.password });
        await bootstrap();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },
  },
  template: `
  <div class="login-wrap">
    <form class="card login-card" @submit.prevent="submit">
      <div class="brand-logo"><Icon name="waveform" size="lg"/></div>
      <h2 style="margin:0 0 4px;letter-spacing:-.02em">VoxDock</h2>
      <p class="muted small" style="margin:0 0 22px">多平台声音克隆工作台</p>
      <div class="input-group" style="margin-bottom:12px">
        <Icon name="lock" size="sm"/>
        <input class="input" type="password" v-model="password" placeholder="管理员密码" autofocus>
      </div>
      <div v-if="error" class="alert alert-error" style="margin-bottom:12px;text-align:left"><Icon name="alert" size="sm"/>{{ error }}</div>
      <button class="btn btn-primary btn-block btn-lg" :disabled="loading || !password">
        <Icon :name="loading ? 'loader' : 'logout'" :class="{ spin: loading }" style="transform:scaleX(-1)"/>登录
      </button>
    </form>
  </div>`,
};

const App = {
  components: { Studio, Voices, History, Providers, ApiDocs, Login, Toasts, ConfirmHost, WavePlayer },
  computed: {
    store: () => store,
    nav: () => NAV,
    current() { return NAV.find((n) => n.path === store.route.path) || NAV[0]; },
    needLogin() { return store.auth.auth_enabled && !store.auth.authenticated; },
    voiceCount() { return store.voices.length; },
  },
  watch: {
    'store.auth.authenticated'(v, old) {
      if (old && !v && store.ready) toast.warn('登录已失效，请重新登录');
    },
    'current.label': {
      immediate: true,
      handler(l) { document.title = `${l} · VoxDock`; },
    },
  },
  methods: {
    navigate,
    toggleTheme() { applyTheme(store.theme === 'dark' ? 'light' : 'dark'); },
    async logout() {
      await api.post('/api/auth/logout');
      await loadAuth();
    },
  },
  template: `
  <div v-if="!store.ready" class="login-wrap"><Icon name="loader" size="xl" class="spin" style="color:var(--accent)"/></div>
  <Login v-else-if="needLogin"/>
  <div v-else class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo"><Icon name="waveform"/></div>
        <div>
          <div class="brand-name">VoxDock</div>
          <div class="brand-sub">声音克隆聚合平台</div>
        </div>
      </div>
      <nav class="nav">
        <template v-for="n in nav" :key="n.path">
          <div v-if="n.section" class="nav-label">{{ n.section }}</div>
          <a class="nav-item" :class="{ active: current.path === n.path }" :href="'#' + n.path">
            <Icon :name="n.icon"/><span class="txt">{{ n.label }}</span>
            <span v-if="n.path === '/voices' && voiceCount" class="count">{{ voiceCount }}</span>
          </a>
        </template>
      </nav>
      <div class="sidebar-foot">
        <div class="provider-dots">
          <div class="tiny muted bold" style="margin-bottom:2px">平台状态</div>
          <div class="provider-dot-row" v-for="p in store.providers" :key="p.name">
            <span class="provider-badge" :style="{ '--c': p.configured && p.enabled ? p.color : '#525a6e' }"><span class="dot"></span></span>
            {{ p.label }}
            <span class="state">{{ !p.configured ? '未配置' : (p.enabled ? '就绪' : '停用') }}</span>
          </div>
        </div>
        <div class="sidebar-actions">
          <button class="btn btn-ghost btn-icon btn-sm" @click="toggleTheme" :title="store.theme === 'dark' ? '浅色模式' : '深色模式'">
            <Icon :name="store.theme === 'dark' ? 'sun' : 'moon'"/>
          </button>
          <a class="btn btn-ghost btn-icon btn-sm" href="/docs" target="_blank" title="API 文档"><Icon name="book"/></a>
          <button v-if="store.auth.auth_enabled" class="btn btn-ghost btn-icon btn-sm" @click="logout" title="退出登录"><Icon name="logout"/></button>
          <span class="ver">v{{ store.system.version }}</span>
        </div>
      </div>
    </aside>
    <main class="main">
      <div class="content">
        <component :is="current.view" :key="current.path"/>
      </div>
    </main>
    <div class="now-playing" v-if="store.nowPlaying">
      <div class="np-info">
        <div class="np-title ellipsis">{{ store.nowPlaying.title }}</div>
        <div class="np-sub ellipsis">{{ store.nowPlaying.subtitle }}</div>
      </div>
      <WavePlayer :key="store.nowPlaying.key" :src="store.nowPlaying.src" :blob="store.nowPlaying.blob" :height="36" compact autoplay style="flex:1;min-width:0"/>
      <a v-if="store.nowPlaying.src" class="btn btn-ghost btn-icon btn-sm" :href="store.nowPlaying.src + (store.nowPlaying.src.includes('/generations/') ? '?download=1' : '')" target="_blank" title="下载"><Icon name="download" size="sm"/></a>
      <button class="btn btn-ghost btn-icon btn-sm" @click="store.nowPlaying = null" title="关闭"><Icon name="x" size="sm"/></button>
    </div>
  </div>
  <Toasts/>
  <ConfirmHost/>`,
};

const app = createApp(App);
app.component('Icon', Icon);
app.component('Modal', Modal);
app.config.errorHandler = (err) => {
  console.error(err);
  toast.error(err && err.message ? err.message : String(err));
};
app.mount('#app');
bootstrap().catch((e) => {
  store.ready = true;
  toast.error('初始化失败：' + e.message);
});
