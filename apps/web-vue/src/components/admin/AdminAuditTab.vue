<script setup lang="ts">
import { computed } from 'vue'
import type { AuditLogEntry, RuntimeHealth } from '@/types'
import Alert from '@/components/ui/Alert.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import Input from '@/components/ui/Input.vue'

interface AuditFilters {
  project_id: string
  actor_user_id: string
  action: string
  limit: number
}

const props = defineProps<{
  entries: AuditLogEntry[]
  total: number
  health: RuntimeHealth | null
  loading: boolean
  error: string
  filters: AuditFilters
  formatDateTime: (value?: string | null) => string
}>()

const emit = defineEmits<{
  refresh: []
  'update:filters': [value: AuditFilters]
}>()

function updateFilters(patch: Partial<AuditFilters>) {
  emit('update:filters', { ...props.filters, ...patch })
}

const projectId = computed({
  get: () => props.filters.project_id,
  set: (value: string | number) => updateFilters({ project_id: String(value || '') }),
})
const actorUserId = computed({
  get: () => props.filters.actor_user_id,
  set: (value: string | number) => updateFilters({ actor_user_id: String(value || '') }),
})
const action = computed({
  get: () => props.filters.action,
  set: (value: string | number) => updateFilters({ action: String(value || '') }),
})
const limit = computed({
  get: () => props.filters.limit,
  set: (value: string | number) => updateFilters({ limit: Number(value || 200) }),
})
</script>

<template>
  <div class="space-y-4">
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Card>
        <p class="text-xs muse-text-muted">平台状态</p>
        <p class="mt-1 text-lg font-semibold" :class="health?.status === 'ok' ? 'text-emerald-600' : 'text-amber-600'">
          {{ health?.status || '—' }}
        </p>
      </Card>
      <Card>
        <p class="text-xs muse-text-muted">PostgreSQL / Redis</p>
        <p class="mt-1 text-sm font-medium">{{ health ? `${health.database} / ${health.redis}` : '—' }}</p>
      </Card>
      <Card>
        <p class="text-xs muse-text-muted">Cognee 项目进程</p>
        <p class="mt-1 text-lg font-semibold">{{ health?.memory.instances ?? '—' }}</p>
      </Card>
      <Card>
        <p class="text-xs muse-text-muted">排队 / 运行</p>
        <p class="mt-1 text-lg font-semibold">{{ health ? `${health.run_counts.queued || 0} / ${health.run_counts.running || 0}` : '—' }}</p>
      </Card>
      <Card>
        <p class="text-xs muse-text-muted">失效 Worker 租约</p>
        <p class="mt-1 text-lg font-semibold" :class="health?.stale_worker_leases ? 'text-red-600' : 'text-emerald-600'">
          {{ health?.stale_worker_leases ?? '—' }}
        </p>
      </Card>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-4">
        <Input v-model="projectId" size="sm" placeholder="项目 ID" />
        <Input v-model="actorUserId" size="sm" placeholder="操作者 ID" />
        <Input v-model="action" size="sm" placeholder="动作（精确匹配）" />
        <Input v-model.number="limit" size="sm" type="number" min="1" max="1000" />
      </div>
      <div class="flex items-center justify-between">
        <p class="text-xs muse-text-muted">共 {{ total }} 条安全审计记录</p>
        <Button size="sm" variant="secondary" :loading="loading" @click="emit('refresh')">刷新</Button>
      </div>
      <Alert v-if="error" variant="destructive">{{ error }}</Alert>
    </Card>

    <Card :stack="false">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
            <tr class="border-b border-stone-300 dark:border-zinc-700">
              <th class="px-3 py-2 text-left text-xs font-medium">时间 / 动作</th>
              <th class="px-3 py-2 text-left text-xs font-medium">操作者 / 项目</th>
              <th class="px-3 py-2 text-left text-xs font-medium">目标 / 请求</th>
              <th class="px-3 py-2 text-left text-xs font-medium">详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in entries" :key="entry.id" class="border-b border-stone-200 dark:border-zinc-800">
              <td class="px-3 py-2 align-top">
                <p class="font-medium">{{ entry.action }}</p>
                <p class="text-xs muse-text-muted">{{ formatDateTime(entry.created_at) }}</p>
              </td>
              <td class="px-3 py-2 align-top font-mono text-xs">
                <p>{{ entry.actor_user_id || 'system' }}</p>
                <p class="mt-1 muse-text-muted">{{ entry.project_id || '—' }}</p>
              </td>
              <td class="px-3 py-2 align-top text-xs">
                <p>{{ entry.target_type }} / {{ entry.target_id || '—' }}</p>
                <p class="mt-1 font-mono muse-text-muted">{{ entry.request_id || '—' }}</p>
                <p class="muse-text-muted">{{ entry.ip_address || '—' }}</p>
              </td>
              <td class="max-w-[420px] px-3 py-2 align-top">
                <pre class="whitespace-pre-wrap break-all text-xs muse-text-muted">{{ JSON.stringify(entry.detail) }}</pre>
              </td>
            </tr>
            <tr v-if="!entries.length">
              <td colspan="4" class="px-3 py-8 text-center muse-text-muted">没有匹配的审计记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
