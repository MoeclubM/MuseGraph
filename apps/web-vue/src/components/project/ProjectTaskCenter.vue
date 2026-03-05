<script setup lang="ts">
import { computed } from 'vue'
import type { OasisTask } from '@/types'
import Alert from '@/components/ui/Alert.vue'
import Button from '@/components/ui/Button.vue'
import Select from '@/components/ui/Select.vue'

type TaskListFilter = 'all' | 'running' | 'completed' | 'failed' | 'cancelled'

const props = defineProps<{
  tasks: OasisTask[]
  loading: boolean
  error: string | null
  expanded: boolean
  filter: TaskListFilter
  cancellingTaskIds: string[]
  formatDate: (value: string) => string
}>()

const emit = defineEmits<{
  'update:expanded': [value: boolean]
  'update:filter': [value: TaskListFilter]
  refresh: []
  cancel: [task: OasisTask]
}>()

function isRunningTaskStatus(status: string): boolean {
  const normalized = String(status || '').toLowerCase()
  return normalized === 'pending' || normalized === 'processing'
}

function isTaskCancellable(task: OasisTask): boolean {
  return isRunningTaskStatus(task.status)
}

function isTaskCancelling(taskId: string): boolean {
  return props.cancellingTaskIds.includes(taskId)
}

function taskTypeLabel(taskType: string): string {
  const labels: Record<string, string> = {
    ontology_generate: 'Ontology',
    graph_build: 'Graph Build',
    oasis_analyze: 'OASIS Analyze',
    oasis_prepare: 'OASIS Prepare',
    oasis_run: 'OASIS Run',
    oasis_report: 'OASIS Report',
  }
  return labels[taskType] || taskType
}

function taskStatusClass(status: string): string {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'completed') return 'text-emerald-700 dark:text-emerald-300'
  if (normalized === 'failed') return 'text-red-700 dark:text-red-300'
  if (normalized === 'cancelled') return 'text-stone-600 dark:text-zinc-400'
  if (normalized === 'processing') return 'text-amber-700 dark:text-amber-300'
  return 'text-stone-700 dark:text-zinc-300'
}

const runningTaskCount = computed(() =>
  props.tasks.filter((task) => isRunningTaskStatus(task.status)).length
)

const filteredTaskList = computed(() => {
  if (props.filter === 'all') return props.tasks
  if (props.filter === 'running') {
    return props.tasks.filter((task) => isRunningTaskStatus(task.status))
  }
  if (props.filter === 'completed') {
    return props.tasks.filter((task) => task.status === 'completed')
  }
  if (props.filter === 'cancelled') {
    return props.tasks.filter((task) => task.status === 'cancelled')
  }
  return props.tasks.filter((task) => task.status === 'failed')
})

const selectedFilter = computed({
  get: () => props.filter,
  set: (value: string | number) => {
    const normalized = String(value || 'all').toLowerCase()
    const filters: TaskListFilter[] = ['all', 'running', 'completed', 'failed', 'cancelled']
    emit('update:filter', filters.includes(normalized as TaskListFilter) ? normalized as TaskListFilter : 'all')
  },
})

function toggleExpanded() {
  emit('update:expanded', !props.expanded)
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed bottom-4 right-4 z-[95] flex flex-col items-end gap-2">
      <div
        v-if="expanded"
        class="w-[min(92vw,428px)] max-h-[72vh] overflow-hidden rounded-2xl border border-stone-300/80 bg-[linear-gradient(180deg,rgba(248,244,234,0.98)_0%,rgba(242,238,229,0.95)_100%)] shadow-2xl backdrop-blur-sm dark:border-zinc-700/70 dark:bg-[linear-gradient(180deg,rgba(24,24,27,0.96)_0%,rgba(20,20,23,0.96)_100%)]"
      >
        <div class="flex items-center justify-between gap-2 border-b border-stone-300/70 px-3 py-2 dark:border-zinc-700/60">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-stone-700 dark:text-zinc-200">
              Task Center
            </p>
            <p class="text-[11px] text-stone-500 dark:text-zinc-500">
              Running {{ runningTaskCount }} / Total {{ tasks.length }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-28">
              <Select v-model="selectedFilter">
                <option value="all">All</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </Select>
            </div>
            <Button
              variant="ghost"
              size="sm"
              :loading="loading"
              @click="emit('refresh')"
            >
              Refresh
            </Button>
          </div>
        </div>

        <div class="max-h-[58vh] overflow-y-auto px-3 py-2 space-y-2">
          <Alert v-if="error" variant="destructive" class="text-xs">
            {{ error }}
          </Alert>

          <div v-if="filteredTaskList.length" class="space-y-1.5">
            <div
              v-for="task in filteredTaskList"
              :key="task.task_id"
              class="rounded-lg border border-stone-300/70 bg-stone-100/80 p-2 space-y-1.5 dark:border-zinc-700/50 dark:bg-zinc-800/45"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-stone-700 dark:text-zinc-200">
                  {{ taskTypeLabel(task.task_type) }}
                </span>
                <span class="text-xs capitalize" :class="taskStatusClass(task.status)">
                  {{ task.status }}
                </span>
              </div>
              <p class="text-[11px] text-stone-600 dark:text-zinc-300 line-clamp-2">
                {{ task.message || '-' }}
              </p>
              <div class="h-1.5 overflow-hidden rounded bg-stone-200/70 dark:bg-zinc-800/70">
                <div
                  class="h-full bg-amber-500 transition-all duration-300"
                  :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress || 0)))}%` }"
                />
              </div>
              <div class="flex items-center justify-between gap-2 text-[10px] text-stone-500 dark:text-zinc-500">
                <span>{{ formatDate(task.updated_at) }}</span>
                <span class="truncate max-w-[180px]">#{{ task.task_id }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <p v-if="task.error" class="min-w-0 flex-1 text-[10px] text-red-700 dark:text-red-300 line-clamp-2">
                  {{ task.error }}
                </p>
                <Button
                  v-if="isTaskCancellable(task)"
                  variant="ghost"
                  size="sm"
                  class="h-6 px-2 text-[10px] text-red-700 hover:text-red-700 dark:text-red-300 dark:hover:text-red-200"
                  :loading="isTaskCancelling(task.task_id)"
                  :disabled="isTaskCancelling(task.task_id)"
                  @click="emit('cancel', task)"
                >
                  Terminate
                </Button>
              </div>
            </div>
          </div>

          <p v-else class="py-3 text-center text-[11px] text-stone-500 dark:text-zinc-500">
            No tasks yet.
          </p>
        </div>
      </div>

      <Button
        variant="primary"
        size="sm"
        class="shadow-xl"
        @click="toggleExpanded"
      >
        Task Center
        <span class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-black/20 px-1.5 text-[10px] text-white">
          {{ runningTaskCount }}
        </span>
      </Button>
    </div>
  </Teleport>
</template>
