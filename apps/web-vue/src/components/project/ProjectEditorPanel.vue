<script setup lang="ts">
import { computed } from 'vue'
import TextEditor from '@/components/editor/TextEditor.vue'

const props = defineProps<{
  visible: boolean
  rightPanelCollapsed: boolean
  chapterTitle: string
  content: string
}>()

const emit = defineEmits<{
  'update:content': [value: string]
}>()

const contentValue = computed({
  get: () => props.content,
  set: (value: string | number) => emit('update:content', String(value || '')),
})
</script>

<template>
  <section
    v-show="visible"
    class="min-w-0 flex-1 bg-[#fbf8f1] dark:bg-zinc-900/30"
    :class="rightPanelCollapsed ? '' : 'border-r border-stone-300/80 dark:border-zinc-700/60'"
  >
    <div class="flex items-center justify-between border-b border-stone-300/70 px-4 py-2 dark:border-zinc-700/60">
      <p class="truncate text-sm font-medium text-stone-700 dark:text-zinc-200">
        {{ chapterTitle || 'Untitled Chapter' }}
      </p>
      <span class="text-xs text-stone-500 dark:text-zinc-500">
        {{ content.length.toLocaleString() }} chars
      </span>
    </div>
    <div class="h-[calc(100%-43px)] p-4">
      <TextEditor v-model="contentValue" placeholder="Write chapter content here..." />
    </div>
  </section>
</template>
