<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="slash-command-popup"
      :style="{ bottom: position.bottom + 'px', left: position.left + 'px' }"
      @mousedown.prevent
    >
      <div class="header">
        {{ headerLabel }}
        <span class="hint">↑↓ 选择 · Enter 确认 · Esc 取消</span>
      </div>
      <ul>
        <li
          v-for="(item, idx) in filtered"
          :key="item.id || item.value || item.slug || item.path"
          :class="{ active: idx === activeIndex }"
          @click="$emit('select', item)"
          @mouseenter="activeIndex = idx"
        >
          <slot name="item" :item="item" :index="idx">
            <span class="label">{{ item.label || item.name || item.slug || item.id }}</span>
            <span v-if="item.description || item.desc" class="desc">{{ item.description || item.desc }}</span>
          </slot>
        </li>
        <li v-if="!filtered.length" class="empty">{{ emptyText }}</li>
      </ul>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  query: string
  items: any[]
  position: { bottom: number; left: number }
  headerLabel: string
  emptyText?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: any): void
  (e: 'dismiss'): void
}>()

const activeIndex = ref(0)
const filtered = computed(() => {
  const q = props.query.toLowerCase()
  if (!q) return props.items.slice(0, 10)
  return props.items
    .filter((item) => {
      const label = String(item.label || item.name || item.slug || item.id || '').toLowerCase()
      const desc = String(item.description || item.desc || '').toLowerCase()
      return label.includes(q) || desc.includes(q)
    })
    .slice(0, 10)
})

watch(() => props.query, () => { activeIndex.value = 0 })
watch(() => props.visible, (v) => { if (v) activeIndex.value = 0 })
watch(() => props.items, () => { activeIndex.value = 0 })

defineExpose({
  moveUp() {
    if (!filtered.value.length) return
    activeIndex.value = (activeIndex.value - 1 + filtered.value.length) % filtered.value.length
  },
  moveDown() {
    if (!filtered.value.length) return
    activeIndex.value = (activeIndex.value + 1) % filtered.value.length
  },
  pickActive() {
    const item = filtered.value[activeIndex.value]
    if (item) emit('select', item)
  },
})
</script>

<style scoped>
.slash-command-popup {
  position: fixed;
  z-index: 9999;
  min-width: 320px;
  max-width: 480px;
  background: var(--muse-panel, #fff);
  border: 1px solid var(--muse-border, #ddd);
  border-radius: 8px;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12);
  padding: 6px 0;
  font-size: 13px;
  max-height: 320px;
  overflow-y: auto;
}
.header {
  font-size: 11px;
  color: var(--muse-text-faint, #888);
  padding: 4px 12px;
  display: flex;
  justify-content: space-between;
}
.header .hint {
  font-size: 10px;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 4px;
}
li.active {
  background: var(--muse-accent-soft, #f0f6ff);
}
li .label {
  font-weight: 500;
}
li .desc {
  font-size: 11px;
  color: var(--muse-text-muted, #777);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
li.empty {
  color: var(--muse-text-faint, #999);
  padding: 8px 12px;
  display: block;
}
</style>