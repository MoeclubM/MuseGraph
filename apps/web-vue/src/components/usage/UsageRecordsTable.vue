<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { UsageRecordListResponse } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'

const props = defineProps<{
  data: UsageRecordListResponse | null
  loading: boolean
  error: string
  page: number
  pageSize: number
  showUser?: boolean
  modelFilter?: string
}>()

const emit = defineEmits<{
  refresh: []
  'apply-filters': []
  'prev-page': []
  'next-page': []
  'update:modelFilter': [value: string]
}>()

const { t } = useI18n()

function formatCost(value?: number): string {
  return Number(value || 0).toFixed(6)
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function userLabel(email?: string | null, nickname?: string | null) {
  if (nickname && email) return `${nickname} · ${email}`
  return nickname || email || '—'
}
</script>

<template>
  <div class="space-y-4">
    <Card class="space-y-3">
      <div class="flex flex-wrap items-end gap-2">
        <div class="w-64 space-y-1">
          <label class="text-xs muse-text-muted">{{ t('usageRecords.filters.model') }}</label>
          <Input
            :model-value="modelFilter || ''"
            :placeholder="t('usageRecords.filters.modelPlaceholder')"
            @update:model-value="emit('update:modelFilter', String($event || ''))"
            @keyup.enter="emit('apply-filters')"
          />
        </div>
        <Button size="sm" variant="secondary" :disabled="loading" @click="emit('refresh')">
          {{ t('common.refresh') }}
        </Button>
        <Button size="sm" @click="emit('apply-filters')">{{ t('admin.common.search') }}</Button>
      </div>
    </Card>

    <Alert v-if="error" variant="destructive">{{ error }}</Alert>

    <Card :stack="false">
      <div v-if="loading" class="p-4 text-sm muse-text-muted">{{ t('usageRecords.loading') }}</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
            <tr class="border-b border-stone-300 dark:border-zinc-700">
              <th class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.time') }}</th>
              <th v-if="showUser" class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.user') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.model') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.project') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('usageRecords.columns.tokens') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('usageRecords.columns.cost') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.billingMode') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('usageRecords.columns.source') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!data?.records?.length">
              <td :colspan="showUser ? 8 : 7" class="px-3 py-8 text-center muse-text-muted">
                {{ t('usageRecords.empty') }}
              </td>
            </tr>
            <tr
              v-for="row in data?.records || []"
              :key="row.id"
              class="border-b border-stone-200/80 dark:border-zinc-800"
            >
              <td class="px-3 py-2 whitespace-nowrap">{{ formatDateTime(row.created_at) }}</td>
              <td v-if="showUser" class="px-3 py-2">{{ userLabel(row.user_email, row.user_nickname) }}</td>
              <td class="px-3 py-2">
                <div class="font-medium">{{ row.model || '—' }}</div>
                <div v-if="row.provider" class="text-xs muse-text-muted">{{ row.provider }}</div>
              </td>
              <td class="px-3 py-2">{{ row.project_title || '—' }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ row.input_tokens }} / {{ row.output_tokens }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">${{ formatCost(row.cost) }}</td>
              <td class="px-3 py-2">{{ row.billing_mode || '—' }}</td>
              <td class="px-3 py-2">{{ row.source || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-if="data && data.total > pageSize"
        class="flex items-center justify-between border-t border-stone-200 px-3 py-2 dark:border-zinc-800"
      >
        <span class="text-xs muse-text-muted">
          {{ t('usageRecords.pagination', { page, total: data.total }) }}
        </span>
        <div class="flex gap-2">
          <Button size="sm" variant="secondary" :disabled="page <= 1" @click="emit('prev-page')">
            {{ t('admin.common.prev') }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="page * pageSize >= data.total"
            @click="emit('next-page')"
          >
            {{ t('admin.common.next') }}
          </Button>
        </div>
      </div>
    </Card>
  </div>
</template>