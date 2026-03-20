<script setup lang="ts">
import { computed } from 'vue'
import type { AdminTask } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'

type TaskStatusFilter = '' | 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'

interface TaskFilters {
  status: TaskStatusFilter
  task_type: string
  project_id: string
  user_id: string
  limit: number
}

const props = defineProps<{
  tasks: AdminTask[]
  total: number
  loading: boolean
  error: string
  message: string
  filters: TaskFilters
  cancellingTaskIds: string[]
  formatDateTime: (value?: string | null) => string
}>()

const emit = defineEmits<{
  refresh: []
  cancel: [task: AdminTask]
  'update:filters': [value: TaskFilters]
}>()

function updateFilters(patch: Partial<TaskFilters>) {
  emit('update:filters', {
    ...props.filters,
    ...patch,
  })
}

const statusFilter = computed({
  get: () => props.filters.status,
  set: (value: TaskStatusFilter) => updateFilters({ status: value }),
})

const taskTypeFilter = computed({
  get: () => props.filters.task_type,
  set: (value: string | number) => updateFilters({ task_type: String(value || '') }),
})

const projectIdFilter = computed({
  get: () => props.filters.project_id,
  set: (value: string | number) => updateFilters({ project_id: String(value || '') }),
})

const userIdFilter = computed({
  get: () => props.filters.user_id,
  set: (value: string | number) => updateFilters({ user_id: String(value || '') }),
})

const limitFilter = computed({
  get: () => props.filters.limit,
  set: (value: string | number) => updateFilters({ limit: Number(value || 200) }),
})

function taskStatusChipClass(value: string) {
  const status = (value || '').toLowerCase()
  if (status === 'completed') {
    return 'border-emerald-300/70 bg-emerald-100 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  if (status === 'processing' || status === 'pending') {
    return 'border-amber-300/80 bg-amber-100 text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (status === 'failed' || status === 'cancelled') {
    return 'border-red-300/80 bg-red-100 text-red-700 dark:border-red-700/50 dark:bg-red-900/20 dark:text-red-300'
  }
  return 'border-stone-300 bg-stone-100 text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function isTaskCancellable(task: AdminTask): boolean {
  const status = String(task.status || '').toLowerCase()
  return status === 'pending' || status === 'processing'
}

function isTaskCancelling(taskId: string): boolean {
  return props.cancellingTaskIds.includes(taskId)
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Task Management</h2>
      <p class="text-xs text-stone-500 dark:text-zinc-400">Inspect, filter, and cancel active system tasks.</p>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-5">
        <Select v-model="statusFilter">
          <option value="">all status</option>
          <option value="pending">pending</option>
          <option value="processing">processing</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
          <option value="cancelled">cancelled</option>
        </Select>
        <Input v-model="taskTypeFilter" placeholder="task_type" />
        <Input v-model="projectIdFilter" placeholder="project_id" />
        <Input v-model="userIdFilter" placeholder="user_id" />
        <Input v-model.number="limitFilter" type="number" min="1" max="1000" />
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" :loading="loading" @click="emit('refresh')">Refresh</Button>
      </div>
      <Alert v-if="error" variant="destructive">{{ error }}</Alert>
      <Alert v-if="message" variant="success">{{ message }}</Alert>
    </Card>

    <Card :stack="false">
      <div class="pb-3 text-xs text-stone-500 dark:text-zinc-400">
        Total: {{ total }}
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
              <tr class="border-b border-stone-300 dark:border-zinc-700">
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Task</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Status</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Progress</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Owner</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Message</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="task in tasks"
                :key="task.task_id"
                class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <td class="px-3 py-2 align-top">
                  <p class="font-medium text-stone-800 dark:text-zinc-100">{{ task.task_type }}</p>
                  <p class="font-mono text-xs text-stone-500 dark:text-zinc-400">{{ task.task_id }}</p>
                  <p class="text-xs text-stone-500 dark:text-zinc-400">{{ formatDateTime(task.updated_at) }}</p>
                </td>
                <td class="px-3 py-2 align-top">
                  <span
                    class="inline-flex rounded-full border px-2 py-0.5 text-xs capitalize"
                    :class="taskStatusChipClass(task.status)"
                  >
                    {{ task.status }}
                  </span>
                </td>
                <td class="px-3 py-2 align-top">
                  <div class="w-28 rounded-full bg-stone-200 dark:bg-zinc-700">
                    <div
                      class="h-1.5 rounded-full bg-amber-500 transition-all duration-300"
                      :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress || 0)))}%` }"
                    />
                  </div>
                  <p class="mt-1 text-xs text-stone-500 dark:text-zinc-400">{{ Number(task.progress || 0) }}%</p>
                </td>
                <td class="px-3 py-2 align-top">
                  <p class="text-xs text-stone-600 dark:text-zinc-300">project: {{ task.metadata?.project_id || '-' }}</p>
                  <p class="text-xs text-stone-600 dark:text-zinc-300">user: {{ task.metadata?.user_id || '-' }}</p>
                </td>
                <td class="px-3 py-2 align-top">
                  <p class="max-w-[340px] text-xs text-stone-700 dark:text-zinc-200 line-clamp-3">{{ task.message || '-' }}</p>
                  <p v-if="task.error" class="max-w-[340px] text-xs text-red-700 dark:text-red-300 line-clamp-3">{{ task.error }}</p>
                </td>
                <td class="px-3 py-2 align-top text-right">
                  <Button
                    v-if="isTaskCancellable(task)"
                    size="sm"
                    variant="danger"
                    :loading="isTaskCancelling(task.task_id)"
                    :disabled="isTaskCancelling(task.task_id)"
                    @click="emit('cancel', task)"
                  >
                    Cancel
                  </Button>
                  <span v-else class="text-xs text-stone-400 dark:text-zinc-500">-</span>
                </td>
              </tr>
              <tr v-if="!tasks.length">
                <td colspan="6" class="px-3 py-8 text-center text-sm text-stone-500 dark:text-zinc-400">
                  No tasks
                </td>
              </tr>
            </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
