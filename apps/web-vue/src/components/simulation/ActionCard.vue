<script setup lang="ts">
import { computed } from 'vue'
import { MessageSquare, Reply, Heart, Share2 } from 'lucide-vue-next'
import type { SimulationAction } from '@/types'

const props = defineProps<{
  action: SimulationAction
  platform?: 'twitter' | 'reddit'
}>()

const platformColor = computed(() => {
  if (props.platform === 'twitter' || props.action.platform === 'twitter') {
    return {
      border: 'border-stone-600',
      bg: 'bg-stone-100/70 dark:bg-zinc-800/50',
      text: 'text-stone-700 dark:text-zinc-200',
    }
  }
  if (props.platform === 'reddit' || props.action.platform === 'reddit') {
    return {
      border: 'border-[#FF4500]',
      bg: 'bg-[#FF4500]/10',
      text: 'text-[#FF4500]',
    }
  }
  return {
    border: 'border-stone-300 dark:border-zinc-700',
    bg: 'bg-stone-100/70 dark:bg-zinc-800/50',
    text: 'text-stone-700 dark:text-zinc-300',
  }
})

const actionIcon = computed(() => {
  const icons: Record<string, any> = {
    post: MessageSquare,
    comment: Reply,
    react: Heart,
    share: Share2,
  }
  return icons[props.action.action_type] || MessageSquare
})

const actionLabel = computed(() => {
  const labels: Record<string, string> = {
    post: '发布',
    comment: '评论',
    react: '反应',
    share: '转发',
  }
  return labels[props.action.action_type] || props.action.action_type
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
      'rounded-lg border-l-4 p-3 transition-all hover:bg-stone-200/60 dark:hover:bg-zinc-800/40',
      platformColor.border,
      platformColor.bg
    ]"
  >
    <div class="flex items-start gap-3">
      <!-- Agent Avatar -->
      <div
        :class="[
          'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
          platformColor.bg,
          platformColor.text
        ]"
      >
        {{ getInitials(action.agent) }}
      </div>

      <div class="flex-1 min-w-0">
        <!-- Header: Agent + Action Type + Time -->
        <div class="flex items-center gap-2 mb-1">
          <span class="font-medium text-sm text-stone-800 dark:text-zinc-100">{{ action.agent }}</span>

          <span
            :class="[
              'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
              platformColor.bg,
              platformColor.text
            ]"
          >
            <component :is="actionIcon" class="w-3 h-3" />
            {{ actionLabel }}
          </span>

          <span class="text-xs text-stone-500 dark:text-zinc-500 ml-auto shrink-0">
            R{{ action.round_num }} · {{ formatTime(action.created_at) }}
          </span>
        </div>

        <!-- Summary Content -->
        <p class="text-sm text-stone-700 dark:text-zinc-300 line-clamp-3">
          {{ action.summary }}
        </p>

        <!-- Platform Badge -->
        <div
          v-if="action.platform"
          class="mt-2"
        >
          <span
            :class="[
              'text-[10px] px-1.5 py-0.5 rounded',
              action.platform === 'twitter'
                ? 'bg-stone-200 text-stone-700 dark:bg-zinc-700 dark:text-zinc-200'
                : 'bg-[#FF4500]/20 text-[#FF4500]'
            ]"
          >
            {{ action.platform === 'twitter' ? 'Twitter' : 'Reddit' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
