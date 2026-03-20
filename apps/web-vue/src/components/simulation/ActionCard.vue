<script setup lang="ts">
import { computed } from 'vue'
import { Activity, ArrowRightCircle, Sparkles, Waypoints } from 'lucide-vue-next'
import type { SimulationAction } from '@/types'

const props = defineProps<{
  action: SimulationAction
}>()

const actionStyle = computed(() => {
  const styles: Record<string, { border: string; bg: string; text: string }> = {
    seed: {
      border: 'border-stone-500',
      bg: 'bg-stone-100/70 dark:bg-zinc-800/50',
      text: 'text-stone-700 dark:text-zinc-200',
    },
    response: {
      border: 'border-amber-500',
      bg: 'bg-amber-100/60 dark:bg-amber-900/20',
      text: 'text-amber-700 dark:text-amber-200',
    },
    signal: {
      border: 'border-rose-500',
      bg: 'bg-rose-100/60 dark:bg-rose-900/20',
      text: 'text-rose-700 dark:text-rose-200',
    },
    amplification: {
      border: 'border-sky-500',
      bg: 'bg-sky-100/60 dark:bg-sky-900/20',
      text: 'text-sky-700 dark:text-sky-200',
    },
    update: {
      border: 'border-emerald-500',
      bg: 'bg-emerald-100/60 dark:bg-emerald-900/20',
      text: 'text-emerald-700 dark:text-emerald-200',
    },
  }
  return styles[props.action.action_kind] || styles.update
})

const actionIcon = computed(() => {
  const icons: Record<string, any> = {
    seed: Sparkles,
    response: ArrowRightCircle,
    signal: Activity,
    amplification: Waypoints,
    update: Activity,
  }
  return icons[props.action.action_kind] || Activity
})

const actionLabel = computed(() => {
  return props.action.action_label || 'State Update'
})

function formatTime(timestamp: string) {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function getInitials(name: string) {
  return name.slice(0, 2).toUpperCase()
}
</script>

<template>
  <div
    :class="[
      'rounded-md border-l-4 p-3 transition-all hover:bg-stone-200/60 dark:hover:bg-zinc-800/40',
      actionStyle.border,
      actionStyle.bg,
    ]"
  >
    <div class="flex items-start gap-3">
      <div
        :class="[
          'h-8 w-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold',
          actionStyle.bg,
          actionStyle.text,
        ]"
      >
        {{ getInitials(action.agent) }}
      </div>

      <div class="min-w-0 flex-1">
        <div class="mb-1 flex items-center gap-2">
          <span class="text-sm font-medium text-stone-800 dark:text-zinc-100">{{ action.agent }}</span>

          <span
            :class="[
              'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium',
              actionStyle.bg,
              actionStyle.text,
            ]"
          >
            <component :is="actionIcon" class="h-3 w-3" />
            {{ actionLabel }}
          </span>

          <span class="ml-auto shrink-0 text-xs text-stone-500 dark:text-zinc-500">
            R{{ action.round_num }} · {{ formatTime(action.created_at) }}
          </span>
        </div>

        <p class="line-clamp-3 text-sm text-stone-700 dark:text-zinc-300">
          {{ action.summary }}
        </p>
      </div>
    </div>
  </div>
</template>
