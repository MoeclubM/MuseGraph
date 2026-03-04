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
    success: 'bg-emerald-900/80 border-emerald-700 text-emerald-100',
    error: 'bg-red-900/80 border-red-700 text-red-100',
    warning: 'bg-amber-900/80 border-amber-700 text-amber-100',
    info: 'bg-stone-900/80 border-stone-700 text-stone-100',
  }
  return colors[props.type]
})

const iconColor = computed(() => {
  const colors: Record<ToastType, string> = {
    success: 'text-emerald-400',
    error: 'text-red-400',
    warning: 'text-amber-400',
    info: 'text-stone-300',
  }
  return colors[props.type]
})
</script>

<template>
  <div
    :class="[colorClasses, 'flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg backdrop-blur-sm']"
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
