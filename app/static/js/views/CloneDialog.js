// 复刻新音色 dialog
import { store, provider, toast, navigate, upsertVoice } from '../store.js';
import { api } from '../api.js';
import { Modal, FormField, StatusPill } from '../components/ui.js';
import { WavePlayer } from '../components/WavePlayer.js';
import { Recorder } from '../components/Recorder.js';
import { fieldsFor, defaultsFor, fmtBytes } from '../utils.js';

export const CloneDialog = {
  name: 'CloneDialog',
  components: { Modal, FormField, StatusPill, WavePlayer, Recorder },
  props: { show: Boolean, initialProvider: String },
  emits: ['close', 'done'],
  data: () => ({
    step: 'form',
    providerName: '',
    form: { name: '', model: '', voice_id: '', transcript: '', demo_text: '', description: '', tags: '' },
    options: {},
    mode: 'upload',
    file: null,
    audioUrl: '',
    over: false,
    showAdv: false,
    submitting: false,
    error: '',
    voice: null,
  }),
  computed: {
    store: () => store,
    prov() { return this.providerName ? provider(this.providerName) : null; },
    fields() { return this.prov ? fieldsFor(this.prov.clone_fields, this.form.model) : []; },
    basicFields() { return this.fields.filter((f) => f.group !== 'advanced'); },
    advFields() { return this.fields.filter((f) => f.group === 'advanced'); },
    modelGroups() {
      const groups = {};
      for (const m of (this.prov && this.prov.models) || []) (groups[m.group || '模型'] ||= []).push(m);
      return groups;
    },
    vidField() { return (this.prov && this.prov.voice_id_field) || { label: '平台音色 ID', placeholder: '留空自动生成' }; },
    accept() { return '.wav,.mp3,.m4a,.ogg,.aac,.flac,.webm,audio/*'; },
    hasAudio() { return this.mode === 'url' ? !!this.audioUrl.trim() : !!this.file; },
    canSubmit() {
      return this.prov && this.prov.configured && this.form.name.trim() && this.hasAudio && !this.submitting &&
        (!this.vidField.required || this.form.voice_id.trim());
    },
  },
  watch: {
    show(v) { if (v) this.reset(); },
    providerName() { this.applyProvider(); },
    'form.model'() { this.options = { ...defaultsFor(this.prov ? this.prov.clone_fields : [], this.form.model), ...this.options }; },
  },
  methods: {
    fmtBytes,
    reset() {
      this.step = 'form';
      this.error = '';
      this.voice = null;
      this.file = null;
      this.audioUrl = '';
      this.mode = 'upload';
      this.form = { name: '', model: '', voice_id: '', transcript: '', demo_text: '', description: '', tags: '' };
      const configured = store.providers.filter((p) => p.configured && p.enabled);
      this.providerName = this.initialProvider || (configured[0] || store.providers[0] || {}).name || '';
      this.applyProvider();
    },
    applyProvider() {
      if (!this.prov) return;
      this.form.model = this.prov.default_model;
      this.options = defaultsFor(this.prov.clone_fields, this.form.model);
      if (this.mode === 'url' && !this.prov.capabilities.audio_url) this.mode = 'upload';
    },
    pickFile() { this.$refs.file.click(); },
    onFile(e) {
      const f = e.target.files && e.target.files[0];
      if (f) this.setFile(f);
      e.target.value = '';
    },
    onDrop(e) {
      this.over = false;
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) this.setFile(f);
    },
    setFile(f) {
      if (f.size > 20 * 1024 * 1024) { toast.error('文件超过 20MB'); return; }
      this.file = f;
      if (!this.form.name) this.form.name = f.name.replace(/\.[^.]+$/, '').slice(0, 40);
    },
    onRecorded(blob, script) {
      this.file = new File([blob], `recording-${Date.now()}.wav`, { type: 'audio/wav' });
      if (!this.form.transcript && script) this.form.transcript = script;
      this.mode = 'upload';
    },
    async submit() {
      if (!this.canSubmit) return;
      this.submitting = true;
      this.error = '';
      const fd = new FormData();
      fd.append('provider', this.providerName);
      for (const [k, v] of Object.entries(this.form)) fd.append(k, v || '');
      fd.append('options', JSON.stringify(this.options));
      if (this.mode === 'url') fd.append('audio_url', this.audioUrl.trim());
      else fd.append('file', this.file, this.file.name || 'audio.wav');
      try {
        const v = await api.upload('/api/voices/clone', fd);
        upsertVoice(v);
        this.voice = v;
        this.step = 'done';
        this.$emit('done', v);
        toast.success(`音色「${v.name}」复刻${v.status === 'training' ? '已提交，正在训练' : '成功'}`);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.submitting = false;
      }
    },
    goStudio() {
      this.$emit('close');
      navigate('/studio', { voice: this.voice.id });
    },
  },
  template: `
  <Modal :show="show" :width="760" @close="$emit('close')" :closable="!submitting">
    <template #head>
      <div class="row" style="gap:12px">
        <div class="brand-logo" style="width:34px;height:34px;border-radius:10px"><Icon name="sparkles" size="sm"/></div>
        <div>
          <div class="modal-title">复刻新音色</div>
          <div class="tiny muted">上传或录制一段参考音频，生成你的专属音色</div>
        </div>
      </div>
    </template>

    <template v-if="step === 'form'">
      <div class="label" style="margin-bottom:8px">选择平台</div>
      <div class="provider-cards">
        <div v-for="p in store.providers" :key="p.name" class="provider-card" :class="{ active: providerName === p.name }"
             :style="{ '--c': p.color }" @click="providerName = p.name">
          <div class="logo">{{ p.label.slice(0, 1) }}</div>
          <div class="pname">{{ p.label }}</div>
          <div class="pvendor">{{ p.vendor }}</div>
          <span v-if="!p.configured" class="badge-soft badge-warn" style="align-self:flex-start;font-size:10.5px">未配置</span>
          <div class="check" v-if="providerName === p.name"><Icon name="check" size="sm" style="width:12px;height:12px"/></div>
        </div>
      </div>

      <div v-if="prov && !prov.configured" class="alert alert-warn" style="margin-top:14px">
        <Icon name="alert" size="sm"/>
        <div>{{ prov.label }} 尚未配置密钥。<a href="#/providers" @click="$emit('close')">前往平台配置 →</a></div>
      </div>

      <template v-if="prov">
        <div class="grid grid-2" style="margin-top:18px">
          <div class="field">
            <label class="label">音色名称<span class="req">*</span></label>
            <input class="input" v-model="form.name" placeholder="例如：小明的声音" maxlength="64">
          </div>
          <div class="field">
            <label class="label">目标模型</label>
            <select class="select" v-model="form.model">
              <optgroup v-for="(items, g) in modelGroups" :key="g" :label="g">
                <option v-for="m in items" :key="m.value" :value="m.value">{{ m.label }}</option>
              </optgroup>
            </select>
          </div>
        </div>
        <div class="field" style="margin-top:14px">
          <label class="label">{{ vidField.label }}<span class="req" v-if="vidField.required">*</span></label>
          <input class="input mono" v-model="form.voice_id" :placeholder="vidField.placeholder">
          <div class="help" v-if="vidField.help">{{ vidField.help }}</div>
        </div>

        <div class="field" style="margin-top:18px">
          <div class="row">
            <label class="label">参考音频<span class="req">*</span></label>
            <div class="spacer"></div>
            <div class="segmented">
              <button :class="{ active: mode === 'upload' }" @click="mode = 'upload'"><Icon name="upload" size="sm"/>上传</button>
              <button :class="{ active: mode === 'record' }" @click="mode = 'record'"><Icon name="mic" size="sm"/>录制</button>
              <button v-if="prov.capabilities.audio_url" :class="{ active: mode === 'url' }" @click="mode = 'url'"><Icon name="link" size="sm"/>URL</button>
            </div>
          </div>
          <template v-if="mode === 'upload'">
            <div v-if="file" class="audio-file">
              <WavePlayer :blob="file" :height="40" compact style="flex:1;min-width:0"/>
              <div class="tiny muted" style="max-width:140px">
                <div class="ellipsis">{{ file.name }}</div>
                <div>{{ fmtBytes(file.size) }}</div>
              </div>
              <button class="btn btn-ghost btn-icon btn-sm" @click="file = null" title="移除"><Icon name="x" size="sm"/></button>
            </div>
            <div v-else class="dropzone" :class="{ over }" @click="pickFile"
                 @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="onDrop">
              <div class="ico"><Icon name="file-audio" size="lg"/></div>
              <div class="bold">点击或拖拽音频文件到这里</div>
              <div class="small muted">支持 {{ prov.clone_audio_formats.join(' / ') }}{{ store.system.ffmpeg ? '，其他格式将自动转换' : '' }}，≤20MB</div>
            </div>
            <input ref="file" type="file" :accept="accept" hidden @change="onFile">
          </template>
          <Recorder v-else-if="mode === 'record'" @recorded="onRecorded"/>
          <template v-else>
            <input class="input" v-model="audioUrl" placeholder="https://example.com/voice.wav">
            <div class="help">需为平台可访问的公网 URL</div>
          </template>
        </div>

        <div class="grid grid-2" style="margin-top:14px">
          <div class="field">
            <label class="label">参考文本 <span class="muted tiny">（可选）</span></label>
            <textarea class="textarea" v-model="form.transcript" rows="3" placeholder="参考音频中说的内容，有助于提升复刻效果"></textarea>
          </div>
          <div class="field">
            <label class="label">试听文本 <span class="muted tiny">（可选）</span></label>
            <textarea class="textarea" v-model="form.demo_text" rows="3" :placeholder="'复刻后用于生成试听音频，例如：' + prov.default_demo_text"></textarea>
          </div>
        </div>

        <div v-if="basicFields.length" class="grid grid-2" style="margin-top:14px;align-items:start">
          <div v-for="f in basicFields" :key="f.key" class="card" style="padding:12px 14px">
            <FormField :field="f" v-model="options[f.key]"/>
          </div>
        </div>

        <div class="param-group-toggle" style="margin-top:14px" @click="showAdv = !showAdv">
          <Icon :name="showAdv ? 'chevron-down' : 'chevron-right'" size="sm"/>更多选项
        </div>
        <div v-if="showAdv" style="margin-top:10px">
          <div class="grid grid-2" style="align-items:start" v-if="advFields.length">
            <div v-for="f in advFields" :key="f.key" class="card" style="padding:12px 14px">
              <FormField :field="f" v-model="options[f.key]"/>
            </div>
          </div>
          <div class="grid grid-2" style="margin-top:14px">
            <div class="field">
              <label class="label">描述</label>
              <input class="input" v-model="form.description" placeholder="例如：温柔知性的女声">
            </div>
            <div class="field">
              <label class="label">标签</label>
              <input class="input" v-model="form.tags" placeholder="逗号分隔，如：女声,温柔">
            </div>
          </div>
        </div>

        <div class="tips" style="margin-top:16px" v-if="prov.clone_tips && prov.clone_tips.length">
          <div class="row bold" style="gap:6px;color:var(--text)"><Icon name="info" size="sm" style="color:var(--info)"/>{{ prov.label }} 复刻提示</div>
          <ul><li v-for="t in prov.clone_tips" :key="t">{{ t }}</li></ul>
        </div>
        <div v-if="error" class="alert alert-error" style="margin-top:14px"><Icon name="alert" size="sm"/><div>{{ error }}</div></div>
      </template>
    </template>

    <template v-else-if="step === 'done' && voice">
      <div class="success-hero">
        <div class="ring"><Icon :name="voice.status === 'training' ? 'clock' : 'check'" size="xl"/></div>
        <div style="font-size:18px;font-weight:700">{{ voice.status === 'training' ? '已提交训练' : '复刻成功' }}</div>
        <div class="row" style="justify-content:center">
          <span class="bold">{{ voice.name }}</span>
          <StatusPill :status="voice.status"/>
        </div>
        <div class="small muted mono">{{ voice.voice_id }}</div>
        <div class="small text-2" v-if="voice.status_message">{{ voice.status_message }}</div>
        <div class="small muted" v-if="voice.status === 'training'">后台会自动查询训练状态，完成后音色库中将更新为「可用」。</div>
      </div>
      <div v-if="voice.has_demo" class="card" style="padding:14px 16px;margin-top:16px">
        <div class="label" style="margin-bottom:8px">平台试听音频</div>
        <WavePlayer :src="'/api/voices/' + voice.id + '/demo'" :height="52"/>
      </div>
    </template>

    <template #foot>
      <template v-if="step === 'form'">
        <button class="btn" @click="$emit('close')" :disabled="submitting">取消</button>
        <button class="btn btn-primary" :disabled="!canSubmit" @click="submit">
          <Icon :name="submitting ? 'loader' : 'sparkles'" :class="{ spin: submitting }"/>{{ submitting ? '复刻中，请稍候…' : '开始复刻' }}
        </button>
      </template>
      <template v-else>
        <button class="btn" @click="reset">继续复刻</button>
        <button class="btn" @click="$emit('close')">完成</button>
        <button class="btn btn-primary" @click="goStudio" :disabled="voice && voice.status === 'failed'"><Icon name="wave"/>去合成</button>
      </template>
    </template>
  </Modal>`,
};
