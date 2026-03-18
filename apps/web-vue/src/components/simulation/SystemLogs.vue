<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { LogEntry } from '@/types'

const props = withDefaults(
  defineProps<{
    logs: LogEntry[]
    maxHeight?: string
    autoScroll?: boolean
  }>(),
  {
    maxHeight: '300px',
    autoScroll: true,
  }
)

const logsContainer = ref<HTMLElement | null>(null)

function getLevelClass(level: LogEntry['level']) {
  const classes = {
    info: 'text-stone-600 dark:text-zinc-400',
    warning: 'text-amber-700 dark:text-amber-300',
    error: 'text-red-700 dark:text-red-300',
    success: 'text-emerald-700 dark:text-emerald-300',
  }
  return classes[level] || classes.info
}

function getLevelBadgeClass(level: LogEntry['level']) {
  const classes = {
    info: 'bg-stone-200 text-stone-700 dark:bg-zinc-700 dark:text-zinc-300',
    warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    error: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  }
  return classes[level] || classes.info
}

function formatTimestamp(timestamp: string) {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-GB', { hour12: false })
  } catch {
    return timestamp
  }
}

// Auto-scroll to bottom when new logs arrive
watch(
  () => props.logs.length,
  async () => {
    if (props.autoScroll) {
      await nextTick()
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    }
  }
)
</script>

<template>
  <div
    ref="logsContainer"
    class="bg-stone-100/75 dark:bg-zinc-900 rounded-lg border border-stone-300/70 dark:border-zinc-700/60 p-1 font-mono text-xs overflow-y-auto custom-scrollbar"
    :style="{ maxHeight }"
  >
    <div v-if="logs.length === 0" class="p-4 text-stone-500 dark:text-zinc-500 text-center">
      No logs yet
    </div>
    <div v-else class="divide-y divide-stone-300/70 dark:divide-zinc-800/50">
      <div
        v-for="log in logs"
        :key="log.id"
        class="rounded-md p-2 hover:bg-stone-200/70 dark:hover:bg-zinc-900/60 transition-colors"
      >
        <div class="flex items-start gap-2">
          <!-- Timestamp -->
          <span class="text-stone-500 dark:text-zinc-500 shrink-0">{{ formatTimestamp(log.timestamp) }}</span>

          <!-- Level badge -->
          <span
            :class="[
              'px-1.5 py-0.5 rounded text-[10px] uppercase font-medium shrink-0',
              getLevelBadgeClass(log.level)
            ]"
          >
            {{ log.level }}
          </span>

          <!-- Source (optional) -->
          <span
            v-if="log.source"
            class="text-stone-500 dark:text-zinc-500 shrink-0"
          >
            [{{ log.source }}]
          </span>

          <!-- Message -->
          <span :class="['flex-1', getLevelClass(log.level)]">
            {{ log.message }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #a8a29e;
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #78716c;
}
</style>
