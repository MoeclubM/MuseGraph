<script setup lang="ts">
import { computed } from 'vue'
import ActionCard from './ActionCard.vue'
import type { SimulationAction } from '@/types'

const props = withDefaults(
  defineProps<{
    actions: SimulationAction[]
    platform?: 'twitter' | 'reddit' | 'all'
    groupByRound?: boolean
    maxHeight?: string
  }>(),
  {
    platform: 'all',
    groupByRound: false,
    maxHeight: '400px',
  }
)

const twitterActions = computed(() =>
  props.actions.filter(a => a.platform === 'twitter')
)

const redditActions = computed(() =>
  props.actions.filter(a => a.platform === 'reddit')
)

const sortedActions = computed(() => {
  if (props.platform === 'twitter') return twitterActions.value
  if (props.platform === 'reddit') return redditActions.value
  return [...props.actions].sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
})

// Group actions by round
const actionsByRound = computed(() => {
  if (!props.groupByRound) return null

  const grouped: Record<number, SimulationAction[]> = {}
  for (const action of sortedActions.value) {
    const round = action.round_num
    if (!grouped[round]) grouped[round] = []
    grouped[round].push(action)
  }

  return Object.entries(grouped)
    .map(([round, actions]) => ({ round: Number(round), actions }))
    .sort((a, b) => b.round - a.round)
})

function getPlatformLabel(platform: string) {
  return platform === 'twitter' ? 'Twitter' : 'Reddit'
}
</script>

<template>
  <div class="w-full">
    <!-- Dual column layout for 'all' platform -->
    <div v-if="platform === 'all'" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Twitter Column -->
      <div>
        <div class="flex items-center gap-2 mb-3">
          <div class="w-3 h-3 rounded-full bg-stone-400" />
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-300">Twitter</h3>
          <span class="text-xs text-stone-500 dark:text-zinc-500">({{ twitterActions.length }})</span>
        </div>
        <div
          class="space-y-2 overflow-y-auto custom-scrollbar pr-2"
          :style="{ maxHeight }"
        >
          <div v-if="twitterActions.length === 0" class="text-sm text-stone-500 dark:text-zinc-500 py-4 text-center">
            暂无 Twitter 动作
          </div>
          <ActionCard
            v-for="action in twitterActions"
            :key="action.action_id"
            :action="action"
            platform="twitter"
          />
        </div>
      </div>

      <!-- Reddit Column -->
      <div>
        <div class="flex items-center gap-2 mb-3">
          <div class="w-3 h-3 rounded-full bg-[#FF4500]" />
          <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-300">Reddit</h3>
          <span class="text-xs text-stone-500 dark:text-zinc-500">({{ redditActions.length }})</span>
        </div>
        <div
          class="space-y-2 overflow-y-auto custom-scrollbar pr-2"
          :style="{ maxHeight }"
        >
          <div v-if="redditActions.length === 0" class="text-sm text-stone-500 dark:text-zinc-500 py-4 text-center">
            暂无 Reddit 动作
          </div>
          <ActionCard
            v-for="action in redditActions"
            :key="action.action_id"
            :action="action"
            platform="reddit"
          />
        </div>
      </div>
    </div>

    <!-- Single column for specific platform -->
    <div v-else>
      <div class="flex items-center gap-2 mb-3">
        <div
          :class="[
            'w-3 h-3 rounded-full',
            platform === 'twitter' ? 'bg-stone-400' : 'bg-[#FF4500]'
          ]"
        />
        <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-300">
          {{ getPlatformLabel(platform) }}
        </h3>
        <span class="text-xs text-stone-500 dark:text-zinc-500">({{ sortedActions.length }})</span>
      </div>

      <!-- Grouped by round -->
      <div
        v-if="actionsByRound"
        class="space-y-4 overflow-y-auto custom-scrollbar pr-2"
        :style="{ maxHeight }"
      >
        <div
          v-for="{ round, actions } in actionsByRound"
          :key="round"
          class="space-y-2"
        >
          <div class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <span class="w-6 h-px bg-stone-300 dark:bg-zinc-700" />
            Round {{ round }}
            <span class="text-stone-500 dark:text-zinc-500">({{ actions.length }})</span>
          </div>
          <ActionCard
            v-for="action in actions"
            :key="action.action_id"
            :action="action"
            :platform="platform"
          />
        </div>
      </div>

      <!-- Simple list -->
      <div
        v-else
        class="space-y-2 overflow-y-auto custom-scrollbar pr-2"
        :style="{ maxHeight }"
      >
        <div v-if="sortedActions.length === 0" class="text-sm text-stone-500 dark:text-zinc-500 py-4 text-center">
          暂无动作
        </div>
        <ActionCard
          v-for="action in sortedActions"
          :key="action.action_id"
          :action="action"
          :platform="platform"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #a8a29e;
  border-radius: 2px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #78716c;
}
</style>
