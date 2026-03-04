<script setup lang="ts">
import { Monitor, Moon, Sun } from 'lucide-vue-next'
import { useTheme, type ThemeMode } from '@/composables/useTheme'

const { themeMode, setTheme } = useTheme()

const options: Array<{ value: ThemeMode; label: string; icon: typeof Sun }> = [
  { value: 'system', label: '跟随系统', icon: Monitor },
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
]
</script>

<template>
  <div class="inline-flex items-center gap-1 rounded-lg border border-stone-300/90 bg-stone-100/90 p-1 dark:border-zinc-700/70 dark:bg-zinc-800/80">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="inline-flex h-7 w-7 items-center justify-center rounded-md text-stone-600 transition-colors hover:bg-stone-200 hover:text-stone-900 dark:text-zinc-300 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
      :class="themeMode === option.value
        ? 'bg-stone-200 text-stone-900 dark:bg-zinc-700 dark:text-zinc-100'
        : ''"
      :title="option.label"
      :aria-label="option.label"
      @click="setTheme(option.value)"
    >
      <component :is="option.icon" class="h-3.5 w-3.5" />
    </button>
  </div>
</template>
