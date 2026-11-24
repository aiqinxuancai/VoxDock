// Voice picker modal grouped by provider
import { store, provider } from '../store.js';
import { Modal, Avatar, StatusPill, ProviderBadge } from './ui.js';

export const VoicePicker = {
  name: 'VoicePicker',
  components: { Modal, Avatar, StatusPill, ProviderBadge },
  props: { show: Boolean, current: Number },
  emits: ['close', 'select'],
  data: () => ({ q: '', tab: '' }),
  computed: {
    filtered() {
      const q = this.q.trim().toLowerCase();
      return store.voices.filter((v) =>
        (!this.tab || v.provider === this.tab) &&
        (!q || v.name.toLowerCase().includes(q) || v.voice_id.toLowerCase().includes(q) || (v.tags || []).some((t) => t.toLowerCase().includes(q))));
    },
    groups() {
      const out = [];
      const favs = this.filtered.filter((v) => v.favorite);
      if (favs.length && !this.tab) out.push({ key: 'fav', label: '收藏', items: favs });
      for (const p of store.providers) {
        const items = this.filtered.filter((v) => v.provider === p.name && (this.tab || !v.favorite));
        if (items.length) out.push({ key: p.name, label: p.label, color: p.color, items });
      }
      return out;
    },
    tabs() { return store.providers.filter((p) => store.voices.some((v) => v.provider === p.name)); },
  },
  watch: { show(v) { if (v) this.$nextTick(() => this.$refs.search && this.$refs.search.focus()); } },
  methods: {
    provider,
    pick(v) {
      if (v.status === 'failed') return;
      this.$emit('select', v);
      this.$emit('close');
    },
  },
  template: `
  <Modal :show="show" title="选择音色" :width="620" @close="$emit('close')">
    <div class="picker">
      <div class="row" style="margin-bottom:12px">
        <div class="input-group" style="flex:1">
          <Icon name="search" size="sm"/>
          <input ref="search" class="input" v-model="q" placeholder="搜索名称、音色 ID、标签…">
        </div>
      </div>
      <div class="segmented" style="margin-bottom:4px" v-if="tabs.length > 1">
        <button :class="{ active: !tab }" @click="tab = ''">全部</button>
        <button v-for="p in tabs" :key="p.name" :class="{ active: tab === p.name }" @click="tab = p.name">{{ p.label }}</button>
      </div>
      <div class="picker-list">
        <template v-for="g in groups" :key="g.key">
          <div class="picker-group">
            <span v-if="g.color" class="provider-badge" :style="{ '--c': g.color }"><span class="dot"></span></span>
            <Icon v-else name="star" size="sm"/>
            {{ g.label }} <span class="muted">· {{ g.items.length }}</span>
          </div>
          <div v-for="v in g.items" :key="g.key + v.id" class="picker-item"
               :class="{ active: v.id === current, disabled: v.status === 'failed' }" @click="pick(v)">
            <Avatar :name="v.name" :color="provider(v.provider).color" small/>
            <div style="flex:1;min-width:0">
              <div class="bold ellipsis">{{ v.name }}</div>
              <div class="tiny muted ellipsis mono">{{ v.voice_id }}</div>
            </div>
            <span class="tag" v-if="v.model">{{ v.model }}</span>
            <StatusPill :status="v.status"/>
            <Icon v-if="v.id === current" name="check" style="color:var(--accent)"/>
          </div>
        </template>
        <div v-if="!groups.length" class="empty" style="padding:40px 0">
          <p>没有匹配的音色</p>
        </div>
      </div>
    </div>
  </Modal>`,
};
