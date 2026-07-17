<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="skill-mention-popup"
      :style="{ top: position.top + 'px', left: position.left + 'px' }"
      @mousedown.prevent
    >
      <div class="header">选择 skill <span class="hint">↑↓ 选择 · Enter 确认 · Esc 取消</span></div>
      <ul>
        <li
          v-for="(item, idx) in filtered"
          :key="item.slug"
          :class="{ active: idx === activeIndex }"
          @click="$emit('select', item)"
          @mouseenter="activeIndex = idx"
        >
          <span class="slug">@{{ item.slug }}</span>
          <span class="name">{{ item.name }}</span>
          <span class="desc">{{ item.description }}</span>
        </li>
        <li v-if="!filtered.length" class="empty">无匹配 skill</li>
      </ul>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SkillItem } from '@/api/skills'

const props = defineProps<{
  visible: boolean
  query: string
  items: SkillItem[]
  position: { top: number; left: number }
}>()

const emit = defineEmits<{
  (e: 'select', skill: SkillItem): void
  (e: 'dismiss'): void
}>()

const activeIndex = ref(0)
const filtered = computed<SkillItem[]>(() => {
  const q = props.query.toLowerCase()
  if (!q) return props.items.slice(0, 8)
  return props.items
    .filter(
      (s) =>
        s.slug.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q),
    )
    .slice(0, 8)
})

watch(() => props.query, () => {
  activeIndex.value = 0
})
watch(() => props.visible, (v) => {
  if (v) activeIndex.value = 0
})

defineExpose({
  moveUp() {
    if (filtered.value.length === 0) return
    activeIndex.value = (activeIndex.value - 1 + filtered.value.length) % filtered.value.length
  },
  moveDown() {
    if (filtered.value.length === 0) return
    activeIndex.value = (activeIndex.value + 1) % filtered.value.length
  },
  pickActive() {
    const item = filtered.value[activeIndex.value]
    if (item) emit('select', item)
  },
})
</script>

<style scoped>
.skill-mention-popup {
  position: fixed;
  z-index: 9999;
  min-width: 320px;
  max-width: 480px;
  background: var(--popup-bg, #fff);
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 6px 0;
  font-size: 13px;
}
.header {
  font-size: 11px;
  color: #888;
  padding: 4px 12px;
  display: flex;
  justify-content: space-between;
}
.header .hint {
  font-size: 10px;
  color: #aaa;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  padding: 6px 12px;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0 8px;
  cursor: pointer;
  border-radius: 4px;
}
li.active {
  background: var(--accent-50, #f0f6ff);
}
li .slug {
  grid-row: 1 / 3;
  font-weight: 600;
  color: var(--accent-600, #2563eb);
  align-self: start;
  margin-top: 2px;
}
li .name {
  font-weight: 500;
  color: #333;
}
li .desc {
  font-size: 11px;
  color: #777;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
li.empty {
  color: #999;
  padding: 8px 12px;
  display: block;
}
</style>
