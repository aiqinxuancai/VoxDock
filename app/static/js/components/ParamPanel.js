// Renders provider TTS params (basic + collapsible advanced)
import { FormField } from './ui.js';
import { fieldsFor } from '../utils.js';

export const ParamPanel = {
  name: 'ParamPanel',
  components: { FormField },
  props: { fields: { type: Array, default: () => [] }, model: String, modelValue: { type: Object, default: () => ({}) } },
  emits: ['update:modelValue'],
  data: () => ({ showAdv: false }),
  computed: {
    visible() { return fieldsFor(this.fields, this.model); },
    basic() { return this.visible.filter((f) => f.group !== 'advanced'); },
    advanced() { return this.visible.filter((f) => f.group === 'advanced'); },
  },
  methods: {
    set(key, v) { this.$emit('update:modelValue', { ...this.modelValue, [key]: v }); },
  },
  template: `
  <div class="params">
    <FormField v-for="f in basic" :key="f.key" :field="f" :model-value="modelValue[f.key]" @update:model-value="set(f.key, $event)" compact/>
    <template v-if="advanced.length">
      <div class="param-group-toggle" @click="showAdv = !showAdv">
        <Icon :name="showAdv ? 'chevron-down' : 'chevron-right'" size="sm"/> 高级参数
        <span class="tiny muted">({{ advanced.length }})</span>
      </div>
      <template v-if="showAdv">
        <FormField v-for="f in advanced" :key="f.key" :field="f" :model-value="modelValue[f.key]" @update:model-value="set(f.key, $event)" compact/>
      </template>
    </template>
    <div v-if="!visible.length" class="small muted">该模型没有可调参数</div>
  </div>`,
};
