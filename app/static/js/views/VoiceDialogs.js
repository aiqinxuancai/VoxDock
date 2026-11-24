// Edit voice / manually add voice dialogs
import { store, provider, toast, upsertVoice } from '../store.js';
import { api } from '../api.js';
import { Modal } from '../components/ui.js';

const EXAMPLES = {
  volcengine: '火山已复刻的 S_xxx 音色；系统音色需将模型改为 seed-tts-2.0 等对应 Resource-Id',
  aliyun: '如 CosyVoice 系统音色 longanyang（模型 cosyvoice-v3-flash），或已有的复刻音色 ID',
  minimax: '如系统音色 male-qn-qingse、female-shaonv，或已复刻的自定义音色 ID',
  zhipu: '如系统音色 tongtong、chuichui、xiaochen，或已复刻的音色 ID',
};

export const EditVoiceDialog = {
  name: 'EditVoiceDialog',
  components: { Modal },
  props: { voice: Object },
  emits: ['close'],
  data: () => ({ form: {}, saving: false }),
  computed: {
    prov() { return this.voice ? provider(this.voice.provider) : null; },
    hasDefaults() { return this.voice && Object.keys(this.voice.default_params || {}).length > 0; },
  },
  watch: {
    voice: {
      immediate: true,
      handler(v) {
        if (v) this.form = { name: v.name, description: v.description, tags: (v.tags || []).join(', '), model: v.model, favorite: v.favorite };
      },
    },
  },
  methods: {
    async save(extra = {}) {
      this.saving = true;
      try {
        const body = {
          ...this.form,
          tags: this.form.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
          ...extra,
        };
        const v = await api.patch(`/api/voices/${this.voice.id}`, body);
        upsertVoice(v);
        toast.success('已保存');
        if (!extra.default_params) this.$emit('close');
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.saving = false;
      }
    },
    clearDefaults() { this.save({ default_params: {} }); },
  },
  template: `
  <Modal :show="!!voice" title="编辑音色" :width="520" @close="$emit('close')">
    <template v-if="voice">
      <div class="field">
        <label class="label">名称</label>
        <input class="input" v-model="form.name" maxlength="64">
      </div>
      <div class="field">
        <label class="label">描述</label>
        <textarea class="textarea" v-model="form.description" rows="2"></textarea>
      </div>
      <div class="field">
        <label class="label">标签</label>
        <input class="input" v-model="form.tags" placeholder="逗号分隔">
      </div>
      <div class="field">
        <label class="label">合成模型</label>
        <input class="input mono" v-model="form.model" list="edit-models">
        <datalist id="edit-models"><option v-for="m in prov.models" :key="m.value" :value="m.value">{{ m.label }}</option></datalist>
        <div class="help">阿里云复刻音色与模型绑定，请勿随意修改</div>
      </div>
      <div class="field">
        <label class="switch"><input type="checkbox" v-model="form.favorite"><span class="track"></span><span>收藏</span></label>
      </div>
      <div class="field" v-if="hasDefaults">
        <label class="label">默认参数</label>
        <div class="row">
          <code class="tag tag-mono ellipsis" style="flex:1;height:auto;padding:6px 8px">{{ JSON.stringify(voice.default_params) }}</code>
          <button class="btn btn-sm" @click="clearDefaults">清除</button>
        </div>
      </div>
      <div class="divider"></div>
      <div class="small muted mono">{{ voice.provider }} · {{ voice.voice_id }}</div>
    </template>
    <template #foot>
      <button class="btn" @click="$emit('close')">取消</button>
      <button class="btn btn-primary" :disabled="saving || !form.name" @click="save()"><Icon name="save" size="sm"/>保存</button>
    </template>
  </Modal>`,
};

export const AddVoiceDialog = {
  name: 'AddVoiceDialog',
  components: { Modal },
  props: { show: Boolean },
  emits: ['close'],
  data: () => ({ form: { provider: '', voice_id: '', name: '', model: '', description: '' }, saving: false }),
  computed: {
    store: () => store,
    prov() { return this.form.provider ? provider(this.form.provider) : null; },
    example() { return EXAMPLES[this.form.provider] || ''; },
  },
  watch: {
    show(v) {
      if (v) {
        const p = store.providers.find((x) => x.configured) || store.providers[0];
        this.form = { provider: p ? p.name : '', voice_id: '', name: '', model: p ? p.default_model : '', description: '' };
      }
    },
    'form.provider'(n) { if (this.prov) this.form.model = this.prov.default_model; },
  },
  methods: {
    async save() {
      this.saving = true;
      try {
        const v = await api.post('/api/voices', this.form);
        upsertVoice(v);
        toast.success('已添加到音色库');
        this.$emit('close');
      } catch (e) {
        toast.error(e.message);
      } finally {
        this.saving = false;
      }
    },
  },
  template: `
  <Modal :show="show" title="添加已有音色" :width="520" @close="$emit('close')">
    <div class="field">
      <label class="label">平台</label>
      <div class="segmented">
        <button v-for="p in store.providers" :key="p.name" :class="{ active: form.provider === p.name }" @click="form.provider = p.name">{{ p.label }}</button>
      </div>
    </div>
    <div class="field">
      <label class="label">平台音色 ID<span class="req">*</span></label>
      <input class="input mono" v-model="form.voice_id" placeholder="voice_id">
      <div class="help">{{ example }}</div>
    </div>
    <div class="field">
      <label class="label">显示名称</label>
      <input class="input" v-model="form.name" placeholder="留空则使用音色 ID">
    </div>
    <div class="field" v-if="prov">
      <label class="label">合成模型</label>
      <input class="input mono" v-model="form.model" list="add-models">
      <datalist id="add-models"><option v-for="m in prov.models" :key="m.value" :value="m.value">{{ m.label }}</option></datalist>
    </div>
    <div class="field">
      <label class="label">描述</label>
      <input class="input" v-model="form.description">
    </div>
    <template #foot>
      <button class="btn" @click="$emit('close')">取消</button>
      <button class="btn btn-primary" :disabled="saving || !form.voice_id.trim()" @click="save"><Icon name="plus" size="sm"/>添加</button>
    </template>
  </Modal>`,
};
