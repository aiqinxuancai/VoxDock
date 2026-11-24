// Thin fetch wrapper for the VoxDock API
import { store } from './store.js';

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function detailOf(data, status) {
  if (!data) return `请求失败 (HTTP ${status})`;
  const d = data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join('；');
  return data.message || `请求失败 (HTTP ${status})`;
}

async function request(method, path, { body, form, raw, signal } = {}) {
  const headers = { 'X-VoxDock-Client': 'web' };
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const res = await fetch(path, { method, headers, body: payload, credentials: 'same-origin', signal });
  if (res.status === 401) {
    store.auth.authenticated = false;
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* not json */ }
    throw new ApiError(detailOf(data, res.status), res.status, data);
  }
  if (raw) return res;
  const ctype = res.headers.get('content-type') || '';
  return ctype.includes('application/json') ? res.json() : res.text();
}

export const api = {
  get: (p, o) => request('GET', p, o),
  post: (p, body, o = {}) => request('POST', p, { ...o, body }),
  put: (p, body, o = {}) => request('PUT', p, { ...o, body }),
  patch: (p, body, o = {}) => request('PATCH', p, { ...o, body }),
  del: (p, o) => request('DELETE', p, o),
  upload: (p, form, o = {}) => request('POST', p, { ...o, form }),
  async blob(method, p, body) {
    const res = await request(method, p, { body, raw: true });
    return { blob: await res.blob(), headers: res.headers };
  },
};
