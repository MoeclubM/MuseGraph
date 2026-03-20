<script setup lang="ts">
import { computed } from 'vue'
import { Network, Columns, LayoutPanelLeft } from 'lucide-vue-next'
import type { ViewMode } from '@/types'

const props = defineProps<{
  mode: ViewMode
}>()

const emit = defineEmits<{
  (e: 'update:mode', value: ViewMode): void
}>()

const modes: Array<{ value: ViewMode; label: string; icon: any }> = [
  { value: 'graph', label: 'Graph', icon: Network },
  { value: 'split', label: 'Split', icon: Columns },
  { value: 'workbench', label: 'Workbench', icon: LayoutPanelLeft },
]
</script>

<template>
  <div class="inline-flex rounded-md bg-stone-100/80 p-1 border border-stone-300/80 dark:bg-zinc-800/70 dark:border-zinc-700/60">
    <button
      v-for="m in modes"
      :key="m.value"
      :class="[
        'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all',
        mode === m.value
          ? 'bg-amber-600 text-white'
          : 'text-stone-600 hover:text-stone-900 hover:bg-stone-200 dark:text-zinc-400 dark:hover:text-zinc-100 dark:hover:bg-zinc-700/50'
      ]"
      @click="emit('update:mode', m.value)"
    >
      <component :is="m.icon" class="w-3.5 h-3.5" />
      {{ m.label }}
    </button>
  </div>
</template>
