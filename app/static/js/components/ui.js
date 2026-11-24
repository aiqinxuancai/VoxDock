// Generic UI building blocks
import { store, dismissToast, provider } from '../store.js';
import { initials } from '../utils.js';

export const Modal = {
  name: 'Modal',
  props: { show: Boolean, title: String, width: { type: [String, Number], default: 560 }, closable: { type: Boolean, default: true } },
  emits: ['close'],
  mounted() { document.addEventListener('keydown', this.onKey); },
  beforeUnmount() { document.removeEventListener('keydown', this.onKey); },
  methods: {
    onKey(e) { if (e.key === 'Escape' && this.show && this.closable) this.$emit('close'); },
    onMask(e) { if (e.target === e.currentTarget && this.closable) this.$emit('close'); },
  },
  template: `
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @mousedown="onMask">
      <div class="modal" :style="{ maxWidth: typeof width === 'number' ? width + 'px' : width }">
        <div class="modal-head" v-if="title || $slots.head">
          <slot name="head"><div class="modal-title">{{ title }}</div></slot>
          <div class="spacer"></div>
          <button v-if="closable" class="btn btn-ghost btn-icon btn-sm" @click="$emit('close')"><Icon name="x"/></button>
        </div>
        <div class="modal-body"><slot/></div>
        <div class="modal-foot" v-if="$slots.foot"><slot name="foot"/></div>
      </div>
    </div>
  </Teleport>`,
};

export const Dropdown = {
  name: 'Dropdown',
  props: { align: { type: String, default: 'right' }, up: Boolean },
  data: () => ({ open: false }),
  mounted() { document.addEventListener('click', this.outside, true); },
  beforeUnmount() { document.removeEventListener('click', this.outside, true); },
  methods: {
    outside(e) { if (this.open && !this.$el.contains(e.target)) this.open = false; },
    toggle() { this.open = !this.open; },
    close() { this.open = false; },
  },
  template: `
  <div class="dropdown">
    <div @click.stop="toggle"><slot name="trigger"/></div>
    <div v-if="open" class="dropdown-menu" :class="{ up, left: align === 'left' }" @click="close"><slot/></div>
  </div>`,
};

export const Toasts = {
  name: 'Toasts',
  setup() { return { store, dismissToast }; },
  computed: { icons: () => ({ success: 'check-circle', error: 'alert', info: 'info', warn: 'alert' }) },
  template: `
  <div class="toasts">
    <div v-for="t in store.toasts" :key="t.id" class="toast" :class="'toast-' + t.type" @click="dismissToast(t.id)">
      <Icon :name="icons[t.type] || 'info'"/>
      <div style="flex:1;word-break:break-word">{{ t.message }}</div>
    </div>
  </div>`,
};

export const ConfirmHost = {
  name: 'ConfirmHost',
  setup() { return { store }; },
  template: `
  <Modal :show="!!store.confirm" :title="store.confirm && store.confirm.title" :width="440"
         @close="store.confirm && store.confirm.resolve(false, false)">
    <template v-if="store.confirm">
      <div class="text-2" style="white-space:pre-line">{{ store.confirm.message }}</div>
      <label v-if="store.confirm.checkbox" class="switch" style="margin-top:16px">
        <input type="checkbox" v-model="store.confirm.checked"><span class="track"></span>
        <span class="small">{{ store.confirm.checkbox }}</span>
      </label>
    </template>
    <template #foot v-if="store.confirm">
      <button class="btn" @click="store.confirm.resolve(false, false)">{{ store.confirm.cancelText }}</button>
      <button class="btn" :class="store.confirm.danger ? 'btn-danger' : 'btn-primary'"
              @click="store.confirm.resolve(true, store.confirm.checked)">{{ store.confirm.confirmText }}</button>
    </template>
  </Modal>`,
};

export const ProviderBadge = {
  name: 'ProviderBadge',
  props: { name: String },
  computed: { p() { return provider(this.name); } },
  template: `<span class="provider-badge" :style="{ '--c': p.color }"><span class="dot"></span>{{ p.label }}</span>`,
};

const STATUS = { ready: '可用', training: '训练中', failed: '失败', unknown: '未知' };
export const StatusPill = {
  name: 'StatusPill',
  props: { status: String, title: String },
  computed: { text() { return STATUS[this.status] || this.status; } },
  template: `<span class="pill" :class="'pill-' + (status || 'unknown')" :title="title">{{ text }}</span>`,
};

export const Avatar = {
  name: 'Avatar',
  props: { name: String, color: String, small: Boolean },
  computed: { txt() { return initials(this.name); } },
  template: `<div class="avatar" :class="{ 'avatar-sm': small }" :style="{ '--c': color || '#8b5cf6' }">{{ txt }}</div>`,
};

export const Empty = {
  name: 'Empty',
  props: { icon: { type: String, default: 'wave' }, title: String, text: String },
  template: `
  <div class="empty">
    <div class="ico"><Icon :name="icon" size="xl"/></div>
    <h3 v-if="title">{{ title }}</h3>
    <p v-if="text">{{ text }}</p>
    <slot/>
  </div>`,
};

/** Dynamic form field driven by the backend Field schema. */
export const FormField = {
  name: 'FormField',
  props: { field: { type: Object, required: true }, modelValue: null, compact: Boolean },
  emits: ['update:modelValue'],
  data: () => ({ reveal: false }),
  computed: {
    value: {
      get() { return this.modelValue ?? (this.field.type === 'switch' ? !!this.field.default : this.field.default ?? ''); },
      set(v) { this.$emit('update:modelValue', v); },
    },
    pct() {
      const f = this.field;
      const v = Number(this.value);
      return `${(((v - f.min) / (f.max - f.min)) * 100).toFixed(1)}%`;
    },
    display() {
      const v = Number(this.value);
      if (isNaN(v)) return this.value;
      return this.field.step && this.field.step < 1 ? v.toFixed(String(this.field.step).split('.')[1]?.length || 2) : v;
    },
  },
  methods: {
    num(e) { const v = e.target.value; this.value = v === '' ? null : Number(v); },
  },
  template: `
  <div class="field">
    <template v-if="field.type === 'switch'">
      <div class="param-inline">
        <div>
          <div class="label" style="margin-bottom:2px">{{ field.label }}</div>
          <div class="help" v-if="field.help && !compact">{{ field.help }}</div>
        </div>
        <label class="switch" :title="field.help"><input type="checkbox" v-model="value"><span class="track"></span></label>
      </div>
    </template>
    <template v-else>
      <label class="label">
        {{ field.label }}<span class="req" v-if="field.required">*</span>
        <span class="val" v-if="field.type === 'slider'">{{ display }}</span>
      </label>
      <input v-if="field.type === 'slider'" class="range" type="range" :min="field.min" :max="field.max" :step="field.step || 1"
             :value="value" @input="value = Number($event.target.value)" :style="{ '--p': pct }"
             @dblclick="value = field.default" title="双击恢复默认">
      <select v-else-if="field.type === 'select'" class="select" v-model="value">
        <option v-for="o in field.options" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
      </select>
      <input v-else-if="field.type === 'number'" class="input" type="number" :min="field.min" :max="field.max" :step="field.step"
             :value="value ?? ''" @input="num" :placeholder="field.placeholder || '默认'">
      <textarea v-else-if="field.type === 'textarea'" class="textarea" v-model="value" :placeholder="field.placeholder" rows="3"></textarea>
      <div v-else-if="field.type === 'password'" class="secret-wrap">
        <input class="input" :type="reveal ? 'text' : 'password'" v-model="value" :placeholder="field.placeholder" autocomplete="off">
        <button type="button" class="btn btn-ghost btn-icon btn-sm eye" @click="reveal = !reveal"><Icon :name="reveal ? 'eye-off' : 'eye'" size="sm"/></button>
      </div>
      <input v-else class="input" v-model="value" :placeholder="field.placeholder">
      <div class="help" v-if="field.help && !compact">{{ field.help }}</div>
    </template>
  </div>`,
};
