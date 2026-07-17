<script setup lang="ts">
import { computed } from 'vue'
import { Loader2, PanelLeftClose, PanelLeftOpen, Plus } from '@lucide/vue'
import { useAgentStore } from '@/stores/agent'

const props = defineProps<{ projectId: string; collapsed: boolean }>()
const emit = defineEmits<{ 'update:collapsed': [value: boolean] }>()
const agent = useAgentStore()

const orderedRuns = computed(() => [...agent.runs].sort(
  (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
))

function statusClass(status: string) {
  if (status === 'completed') return 'bg-emerald-500'
  if (status === 'failed' || status === 'conflicted') return 'bg-red-500'
  if (status === 'awaiting_review') return 'bg-blue-500'
  if (status === 'cancelled' || status === 'rejected') return 'bg-slate-400'
  return 'bg-amber-500'
}
</script>

<template>
  <aside class="muse-workspace-sidebar" data-testid="agent-run-sidebar">
    <div v-if="collapsed" class="flex h-full flex-col items-center gap-2 py-3">
      <button class="muse-icon-btn" type="button" @click="emit('update:collapsed', false)">
        <PanelLeftOpen class="h-4 w-4" />
      </button>
      <button class="muse-icon-btn" type="button" @click="agent.startNewRun()">
        <Plus class="h-4 w-4" />
      </button>
    </div>

    <template v-else>
      <div class="muse-workspace-sidebar-header">
        <h2 class="muse-text-overline">创作运行</h2>
        <button class="muse-icon-btn !h-7 !w-7" type="button" @click="emit('update:collapsed', true)">
          <PanelLeftClose class="h-3.5 w-3.5" />
        </button>
      </div>
      <div class="muse-workspace-sidebar-body">
        <button class="muse-workspace-new-agent-btn muse-focus-ring" type="button" @click="agent.startNewRun()">
          <Plus class="h-3.5 w-3.5" />
          新建运行
        </button>
      </div>
      <div class="muse-workspace-list space-y-1" data-testid="agent-run-list">
        <div v-if="agent.loading" class="flex justify-center py-8">
          <Loader2 class="h-4 w-4 animate-spin muse-text-faint" />
        </div>
        <p v-else-if="!orderedRuns.length" class="px-3 py-8 text-center text-xs muse-text-faint">
          暂无运行记录
        </p>
        <button
          v-for="run in orderedRuns"
          :key="run.id"
          type="button"
          class="muse-workspace-list-item w-full text-left"
          :class="{ 'muse-workspace-list-item-active': agent.currentRunId === run.id }"
          @click="agent.selectRun(props.projectId, run.id)"
        >
          <span class="h-2 w-2 shrink-0 rounded-full" :class="statusClass(run.status)" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-xs font-medium muse-text-body">{{ run.instruction }}</span>
            <span class="block truncate text-[11px] muse-text-faint">{{ run.mode }} · {{ run.status }}</span>
          </span>
        </button>
      </div>
    </template>
  </aside>
</template>
