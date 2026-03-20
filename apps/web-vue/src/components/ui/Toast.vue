<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-vue-next'
import type { ToastType } from '@/types'

const props = defineProps<{
  message: string
  type: ToastType
}>()

const emit = defineEmits<{
  close: []
}>()

const icon = computed(() => {
  const icons = { success: CheckCircle, error: XCircle, warning: AlertTriangle, info: Info }
  return icons[props.type]
})

const colorClasses = computed(() => {
  const colors: Record<ToastType, string> = {
    success: 'bg-emerald-100 border-emerald-300/80 text-emerald-900 dark:bg-emerald-900/20 dark:border-emerald-700/50 dark:text-emerald-200',
    error: 'bg-red-100 border-red-300/80 text-red-800 dark:bg-red-900/20 dark:border-red-700/50 dark:text-red-200',
    warning: 'bg-amber-100 border-amber-300/80 text-amber-900 dark:bg-amber-900/20 dark:border-amber-700/50 dark:text-amber-200',
    info: 'bg-stone-100 border-stone-300/80 text-stone-800 dark:bg-zinc-800 dark:border-zinc-700/60 dark:text-stone-100',
  }
  return colors[props.type]
})

const iconColor = computed(() => {
  const colors: Record<ToastType, string> = {
    success: 'text-emerald-700 dark:text-emerald-300',
    error: 'text-red-700 dark:text-red-300',
    warning: 'text-amber-700 dark:text-amber-300',
    info: 'text-stone-600 dark:text-zinc-300',
  }
  return colors[props.type]
})
</script>

<template>
  <div
    :class="[colorClasses, 'flex items-center gap-3 px-4 py-3 rounded-md border shadow-none']"
  >
    <component :is="icon" class="w-5 h-5 shrink-0" :class="iconColor" />
    <span class="text-sm flex-1">{{ message }}</span>
    <button class="shrink-0 opacity-60 hover:opacity-100 transition-opacity" @click="emit('close')">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  </div>
</template>
