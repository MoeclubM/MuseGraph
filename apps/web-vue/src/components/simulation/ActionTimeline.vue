<script setup lang="ts">
import { computed } from 'vue'
import ActionCard from './ActionCard.vue'
import type { SimulationAction } from '@/types'

const props = withDefaults(
  defineProps<{
    actions: SimulationAction[]
    groupByRound?: boolean
    maxHeight?: string
  }>(),
  {
    groupByRound: false,
    maxHeight: '400px',
  }
)

const sortedActions = computed(() =>
  [...props.actions].sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
)

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
</script>

<template>
  <div class="w-full">
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
        <div class="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-zinc-400">
          <span class="h-px w-6 bg-stone-300 dark:bg-zinc-700" />
          Iteration {{ round }}
          <span class="text-stone-500 dark:text-zinc-500">({{ actions.length }})</span>
        </div>
        <ActionCard
          v-for="action in actions"
          :key="action.action_id"
          :action="action"
        />
      </div>
    </div>

    <div
      v-else
      class="space-y-2 overflow-y-auto custom-scrollbar pr-2"
      :style="{ maxHeight }"
    >
      <div v-if="sortedActions.length === 0" class="py-4 text-center text-sm text-stone-500 dark:text-zinc-500">
        No analysis timeline entries yet.
      </div>
      <ActionCard
        v-for="action in sortedActions"
        :key="action.action_id"
        :action="action"
      />
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
