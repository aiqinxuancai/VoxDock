// API 接入：API Key 管理 + 调用示例
import { store, toast, confirmDialog } from '../store.js';
import { api } from '../api.js';
import { Modal } from '../components/ui.js';
import { copyText, timeAgo } from '../utils.js';

const ENDPOINTS = [
  ['GET', '/api/voices', '音色列表（支持 provider / status / q 筛选）'],
  ['POST', '/api/voices/clone', '上传参考音频复刻新音色（multipart）'],
  ['POST', '/api/voices', '添加已有平台音色到音色库'],
  ['GET', '/api/voices/{id}', '音色详情'],
  ['PATCH', '/api/voices/{id}', '编辑音色（名称/标签/默认参数）'],
  ['DELETE', '/api/voices/{id}?remote=true', '删除音色（可同时删除平台音色）'],
  ['POST', '/api/voices/{id}/refresh', '刷新训练状态'],
  ['POST', '/api/tts', '合成语音：output=audio 直接返回音频，url/base64 返回 JSON'],
  ['GET', '/api/tts?voice=&text=', 'GET 方式合成，直接返回音频'],
  ['GET', '/api/generations', '合成历史'],
  ['GET', '/api/generations/{id}/audio', '下载历史音频'],
  ['GET', '/api/providers', '平台列表及参数定义（tts_params）'],
  ['POST', '/api/providers/{name}/sync', '从平台同步音色'],
  ['POST', '/v1/audio/speech', 'OpenAI 兼容接口（可直接使用 OpenAI SDK）'],
];

export const ApiDocs = {
  name: 'ApiDocs',
  components: { Modal },
  data: () => ({ keys: [], staticKeys: 0, newName: '', creating: false, created: null, tab: 'curl', loadError: '' }),
  computed: {
    store: () => store,
    base() { return location.origin; },
    sampleVoice() { const v = store.voices.find((x) => x.status === 'ready') || store.voices[0]; return v ? v.id : 1; },
    keyHint() { return this.created ? this.created.key : 'vd-your-api-key'; },
    endpoints: () => ENDPOINTS,
    examples() {
      const B = this.base, K = this.keyHint, V = this.sampleVoice;
      return {
        curl: `# 1) 获取音色列表
curl ${B}/api/voices -H "Authorization: Bearer ${K}"

# 2) 合成语音（直接返回音频文件）
curl -X POST ${B}/api/tts \\
  -H "Authorization: Bearer ${K}" \\
  -H "Content-Type: application/json" \\
  -d '{"voice": ${V}, "text": "你好，欢迎使用 VoxDock", "speed": 1.1, "format": "mp3"}' \\
  -o output.mp3

# 3) GET 方式（适合嵌入 <audio> / 物联网设备）
curl "${B}/api/tts?voice=${V}&text=你好&api_key=${K}" -o output.mp3

# 4) 直接使用平台系统音色（无需入库）
curl -X POST ${B}/api/tts -H "Authorization: Bearer ${K}" -H "Content-Type: application/json" \\
  -d '{"voice": "minimax:male-qn-qingse", "text": "你好"}' -o output.mp3

# 5) 复刻新音色
curl -X POST ${B}/api/voices/clone \\
  -H "Authorization: Bearer ${K}" \\
  -F provider=minimax -F name=我的声音 -F file=@sample.wav`,
        python: `import requests

BASE = "${B}"
HEADERS = {"Authorization": "Bearer ${K}"}

# 音色列表
voices = requests.get(f"{BASE}/api/voices", headers=HEADERS).json()["items"]
for v in voices:
    print(v["id"], v["provider"], v["name"], v["status"])

# 合成语音
resp = requests.post(f"{BASE}/api/tts", headers=HEADERS, json={
    "voice": ${V},
    "text": "你好，欢迎使用 VoxDock",
    "params": {"speed": 1.1},
})
resp.raise_for_status()
open("output.mp3", "wb").write(resp.content)

# 复刻新音色
with open("sample.wav", "rb") as f:
    voice = requests.post(f"{BASE}/api/voices/clone", headers=HEADERS,
                          data={"provider": "aliyun", "name": "我的声音", "model": "cosyvoice-v3-plus"},
                          files={"file": f}).json()
print(voice["id"], voice["status"])`,
        javascript: `const BASE = "${B}";
const headers = { Authorization: "Bearer ${K}", "Content-Type": "application/json" };

const res = await fetch(\`\${BASE}/api/tts\`, {
  method: "POST",
  headers,
  body: JSON.stringify({ voice: ${V}, text: "你好，欢迎使用 VoxDock", output: "url" }),
});
const data = await res.json();          // { audio_url, duration_ms, generation, ... }
new Audio(BASE + data.audio_url).play(); // 浏览器中需同源或携带 api_key 参数`,
        openai: `# pip install openai
from openai import OpenAI

client = OpenAI(base_url="${B}/v1", api_key="${K}")

with client.audio.speech.with_streaming_response.create(
    model="tts-1",          # 忽略；填 provider 名（如 minimax）可强制平台
    voice="${V}",             # 音色库 ID / 平台音色 ID / 名称 / provider:voice_id
    input="你好，这是 OpenAI 兼容接口",
    speed=1.0,
) as response:
    response.stream_to_file("output.mp3")`,
      };
    },
  },
  mounted() { this.load(); },
  methods: {
    timeAgo,
    async load() {
      try {
        const r = await api.get('/api/keys');
        this.keys = r.items;
        this.staticKeys = r.static_keys;
        this.loadError = '';
      } catch (e) {
        this.loadError = e.message;
      }
    },
    async create() {
      this.creating = true;
      try {
        this.created = await api.post('/api/keys', { name: this.newName.trim() || 'default' });
        this.newName = '';
        this.load();
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.creating = false;
      }
    },
    async remove(k) {
      const ok = await confirmDialog({ title: '删除 API Key', message: `删除后使用「${k.name}」的应用将无法继续调用。`, confirmText: '删除', danger: true });
      if (!ok) return;
      await api.del(`/api/keys/${k.id}`);
      this.load();
    },
    copy(t, msg = '已复制') { copyText(t); toast.success(msg); },
  },
  template: `
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">API 接入</h1>
        <p class="page-desc">通过简洁的 REST API 获取音色、复刻声音、合成音频；兼容 OpenAI TTS 接口。</p>
      </div>
      <div class="page-actions">
        <a class="btn" href="/docs" target="_blank"><Icon name="book" size="sm"/>Swagger 文档</a>
        <a class="btn" href="/redoc" target="_blank"><Icon name="external" size="sm"/>ReDoc</a>
      </div>
    </div>

    <div class="alert alert-warn" style="margin-bottom:16px" v-if="!store.auth.auth_enabled">
      <Icon name="lock" size="sm"/>
      <div>当前未设置 <code>VOXDOCK_ADMIN_PASSWORD</code>，Web 与 API 均无需鉴权。部署到公网前请务必设置管理员密码，之后 API 需携带 API Key 调用。</div>
    </div>

    <div class="studio">
      <div class="col" style="gap:16px">
        <div class="card">
          <div class="card-head">
            <div class="card-title"><Icon name="code" size="sm"/>调用示例</div>
            <div class="spacer"></div>
            <div class="segmented">
              <button :class="{ active: tab === 'curl' }" @click="tab = 'curl'">cURL</button>
              <button :class="{ active: tab === 'python' }" @click="tab = 'python'">Python</button>
              <button :class="{ active: tab === 'javascript' }" @click="tab = 'javascript'">JavaScript</button>
              <button :class="{ active: tab === 'openai' }" @click="tab = 'openai'">OpenAI SDK</button>
            </div>
          </div>
          <div class="card-body">
            <div class="code-wrap">
              <pre class="code">{{ examples[tab] }}</pre>
              <button class="btn btn-sm copy" @click="copy(examples[tab])"><Icon name="copy" size="sm"/>复制</button>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="card-title"><Icon name="terminal" size="sm"/>接口一览</div></div>
          <div class="card-body">
            <div class="endpoint" v-for="e in endpoints" :key="e[0] + e[1]">
              <span class="method" :class="'m-' + e[0].toLowerCase()">{{ e[0] }}</span>
              <code class="small" style="min-width:260px">{{ e[1] }}</code>
              <span class="small muted">{{ e[2] }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="col" style="gap:16px">
        <div class="card">
          <div class="card-head"><div class="card-title"><Icon name="key" size="sm"/>API Key</div></div>
          <div class="card-body">
            <div v-if="loadError" class="alert alert-error"><Icon name="alert" size="sm"/>{{ loadError }}</div>
            <template v-else>
              <div class="row">
                <input class="input" v-model="newName" placeholder="Key 名称，如：my-app" @keydown.enter="create">
                <button class="btn btn-primary" :disabled="creating" @click="create"><Icon name="plus" size="sm"/>创建</button>
              </div>
              <div style="margin-top:12px">
                <div v-for="k in keys" :key="k.id" class="key-row">
                  <div class="ico" style="width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--grad-soft);color:var(--accent)"><Icon name="key" size="sm"/></div>
                  <div style="flex:1;min-width:0">
                    <div class="bold small">{{ k.name }}</div>
                    <div class="tiny muted mono">{{ k.prefix }}•••••• · {{ k.last_used_at ? '最近使用 ' + timeAgo(k.last_used_at) : '未使用' }}</div>
                  </div>
                  <button class="btn btn-ghost btn-icon btn-sm btn-danger" @click="remove(k)"><Icon name="trash" size="sm"/></button>
                </div>
                <div v-if="!keys.length" class="small muted" style="padding:14px 0">还没有 API Key</div>
                <div v-if="staticKeys" class="tiny muted" style="margin-top:8px">另有 {{ staticKeys }} 个来自环境变量 VOXDOCK_API_KEYS 的 Key</div>
              </div>
            </template>
          </div>
        </div>
        <div class="card card-pad">
          <div class="card-title" style="margin-bottom:10px"><Icon name="info" size="sm"/>鉴权方式（任选其一）</div>
          <div class="small text-2 col" style="gap:6px">
            <div><code>Authorization: Bearer vd-xxx</code></div>
            <div><code>X-API-Key: vd-xxx</code></div>
            <div><code>?api_key=vd-xxx</code>（URL 参数）</div>
          </div>
          <div class="divider"></div>
          <div class="card-title" style="margin-bottom:10px"><Icon name="wave" size="sm"/>voice 参数</div>
          <div class="small text-2 col" style="gap:6px">
            <div>• 音色库 ID：<code>12</code></div>
            <div>• 平台音色 ID：<code>S_abc123</code></div>
            <div>• 音色名称：<code>小明的声音</code></div>
            <div>• 平台前缀：<code>zhipu:tongtong</code>（无需入库）</div>
          </div>
          <div class="divider"></div>
          <div class="small text-2">参数（speed / volume / pitch / format / emotion…）以各平台定义为准，可通过 <code>GET /api/providers</code> 查看 <code>tts_params</code>。</div>
        </div>
      </div>
    </div>

    <Modal :show="!!created" title="API Key 已创建" :width="520" @close="created = null">
      <template v-if="created">
        <div class="alert alert-warn" style="margin-bottom:14px"><Icon name="alert" size="sm"/>请立即复制保存，关闭后将无法再次查看完整 Key。</div>
        <div class="new-key">{{ created.key }}</div>
      </template>
      <template #foot>
        <button class="btn" @click="created = null">关闭</button>
        <button class="btn btn-primary" @click="copy(created.key, '已复制 API Key')"><Icon name="copy" size="sm"/>复制</button>
      </template>
    </Modal>
  </div>`,
};
