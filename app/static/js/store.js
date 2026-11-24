// Global reactive store, toasts, confirm dialog and a tiny hash router
import { reactive, computed } from '../vendor/vue.esm-browser.prod.js';
import { api } from './api.js';

export const store = reactive({
  ready: false,
  auth: { auth_enabled: false, authenticated: true },
  system: { version: '', ffmpeg: false, stats: {} },
  providers: [],
  voices: [],
  voicesLoaded: false,
  theme: localStorage.getItem('voxdock.theme') || 'dark',
  toasts: [],
  confirm: null,
  nowPlaying: null, // { title, subtitle, src, blob, key }
  route: { path: '/studio', query: {} },
});

export const providerMap = computed(() => Object.fromEntries(store.providers.map((p) => [p.name, p])));

export function provider(name) {
  return providerMap.value[name] || { name, label: name, color: '#64748b', tts_params: [], models: [] };
}

// --------------------------------------------------------------- toasts
let toastId = 0;
export function toast(message, type = 'info', timeout = 3600) {
  const id = ++toastId;
  store.toasts.push({ id, message, type });
  if (timeout) setTimeout(() => dismissToast(id), timeout);
}
toast.success = (m) => toast(m, 'success');
toast.error = (m) => toast(m, 'error', 6000);
toast.warn = (m) => toast(m, 'warn', 5000);
export function dismissToast(id) {
  const i = store.toasts.findIndex((t) => t.id === id);
  if (i >= 0) store.toasts.splice(i, 1);
}

// -------------------------------------------------------------- confirm
export function confirmDialog(opts) {
  return new Promise((resolve) => {
    store.confirm = {
      title: '确认操作',
      confirmText: '确定',
      cancelText: '取消',
      danger: false,
      checkbox: null,
      ...opts,
      checked: false,
      resolve: (ok, checked) => { store.confirm = null; resolve(opts.checkbox ? { ok, checked } : ok); },
    };
  });
}

// --------------------------------------------------------------- router
function parseHash() {
  const h = location.hash.replace(/^#/, '') || '/studio';
  const [path, qs] = h.split('?');
  store.route = { path: path || '/studio', query: Object.fromEntries(new URLSearchParams(qs || '')) };
}
window.addEventListener('hashchange', parseHash);
parseHash();

export function navigate(path, query) {
  const qs = query ? '?' + new URLSearchParams(query).toString() : '';
  location.hash = path + qs;
}

// ---------------------------------------------------------------- theme
export function applyTheme(t) {
  store.theme = t;
  document.documentElement.dataset.theme = t;
  localStorage.setItem('voxdock.theme', t);
}
applyTheme(store.theme);

// -------------------------------------------------------------- actions
export async function loadAuth() {
  store.auth = await api.get('/api/auth/status');
  return store.auth;
}

export async function loadProviders() {
  const res = await api.get('/api/providers');
  store.providers = res.items;
}

export async function loadVoices() {
  const res = await api.get('/api/voices');
  store.voices = res.items;
  store.voicesLoaded = true;
}

export async function loadSystem() {
  store.system = await api.get('/api/system');
}

export function upsertVoice(v) {
  const i = store.voices.findIndex((x) => x.id === v.id);
  if (i >= 0) store.voices.splice(i, 1, v);
  else store.voices.unshift(v);
}

export function removeVoice(id) {
  const i = store.voices.findIndex((x) => x.id === id);
  if (i >= 0) store.voices.splice(i, 1);
}

export async function bootstrap() {
  await loadAuth();
  if (store.auth.authenticated) {
    await Promise.all([loadProviders(), loadVoices(), loadSystem()]);
  }
  store.ready = true;
}

export function play(item) {
  store.nowPlaying = { key: Date.now(), ...item };
}
