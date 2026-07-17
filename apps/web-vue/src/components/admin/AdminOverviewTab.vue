<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { StatsResponse } from '@/types'
import Card from '@/components/ui/Card.vue'

defineProps<{
  stats: StatsResponse | null
  formatCurrency: (value?: number, digits?: number) => string
  formatTokens: (value?: number) => string
}>()

const { t } = useI18n()
</script>

<template>
  <div class="space-y-3">
    <div class="muse-stat-grid-dense">
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.users') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ stats?.total_users ?? 0 }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.projects') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ stats?.total_projects ?? 0 }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.operations') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ stats?.total_operations ?? 0 }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.revenue') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ formatCurrency(stats?.total_revenue, 2) }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.usageCost') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ formatCurrency(stats?.total_usage_cost) }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.totalTokens') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ formatTokens(stats?.total_tokens) }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.tokens24h') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ formatTokens(stats?.last_24h_tokens) }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.totalBalance') }}</p>
        <p class="text-lg font-semibold leading-tight muse-text-heading">{{ formatCurrency(stats?.total_balance) }}</p>
      </Card>
    </div>

    <div class="grid gap-2 sm:grid-cols-3">
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.requests24h') }}</p>
        <p class="text-base font-semibold leading-tight muse-text-heading">{{ stats?.last_24h_request_count ?? 0 }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.cost7d') }}</p>
        <p class="text-base font-semibold leading-tight muse-text-heading">{{ formatCurrency(stats?.last_7d_cost) }}</p>
      </Card>
      <Card variant="stat" class="muse-card-stat-compact space-y-0.5" :stack="false">
        <p class="text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('admin.overview.cost30d') }}</p>
        <p class="text-base font-semibold leading-tight muse-text-heading">{{ formatCurrency(stats?.last_30d_cost) }}</p>
      </Card>
    </div>

    <div class="grid gap-3 md:grid-cols-2">
      <Card variant="compact" :stack="false">
        <div class="border-b border-[color:var(--muse-border)] pb-2">
          <p class="text-sm font-medium muse-text-body">{{ t('admin.overview.topUsersByCost') }}</p>
        </div>
        <div class="overflow-x-auto pt-3">
          <table class="w-full text-sm">
            <thead class="bg-[color:var(--muse-bg-soft)]">
              <tr class="border-b border-[color:var(--muse-border)]">
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.user') }}</th>
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.requests') }}</th>
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.tokens') }}</th>
                <th class="px-2 py-1.5 text-right text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in stats?.top_users ?? []"
                :key="u.user_id"
                class="border-b border-[color:var(--muse-border)]"
              >
                <td class="px-2 py-1.5 muse-text-body">
                  <p class="max-w-[200px] truncate text-xs">{{ u.nickname || u.email }}</p>
                  <p class="max-w-[200px] truncate text-[10px] muse-text-muted">{{ u.email }}</p>
                </td>
                <td class="px-2 py-1.5 text-xs muse-text-muted">{{ u.request_count }}</td>
                <td class="px-2 py-1.5 text-xs muse-text-muted">{{ formatTokens(u.total_tokens) }}</td>
                <td class="px-2 py-1.5 text-right text-xs muse-text-body">{{ formatCurrency(u.cost) }}</td>
              </tr>
              <tr v-if="!(stats?.top_users?.length)">
                <td colspan="4" class="px-2 py-2 text-center text-xs muse-text-muted">{{ t('admin.overview.noUsageData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <Card variant="compact" :stack="false">
        <div class="border-b border-[color:var(--muse-border)] pb-2">
          <p class="text-sm font-medium muse-text-body">{{ t('admin.overview.topModelsByCost') }}</p>
        </div>
        <div class="overflow-x-auto pt-3">
          <table class="w-full text-sm">
            <thead class="bg-[color:var(--muse-bg-soft)]">
              <tr class="border-b border-[color:var(--muse-border)]">
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.modelLabel') }}</th>
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.requests') }}</th>
                <th class="px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.tokens') }}</th>
                <th class="px-2 py-1.5 text-right text-[10px] font-medium uppercase tracking-wide muse-text-faint">{{ t('common.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="m in stats?.top_models ?? []"
                :key="m.model"
                class="border-b border-[color:var(--muse-border)]"
              >
                <td class="px-2 py-1.5 font-mono text-[11px] muse-text-body">{{ m.model }}</td>
                <td class="px-2 py-1.5 text-xs muse-text-muted">{{ m.request_count }}</td>
                <td class="px-2 py-1.5 text-xs muse-text-muted">{{ formatTokens(m.total_tokens) }}</td>
                <td class="px-2 py-1.5 text-right text-xs muse-text-body">{{ formatCurrency(m.cost) }}</td>
              </tr>
              <tr v-if="!(stats?.top_models?.length)">
                <td colspan="4" class="px-2 py-2 text-center text-xs muse-text-muted">{{ t('admin.overview.noModelData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>

    <Card variant="compact" class="space-y-2">
      <p class="text-sm font-medium muse-text-body">{{ t('admin.overview.usageAudit') }}</p>
      <div class="grid gap-1.5 text-xs muse-text-muted md:grid-cols-2">
        <div>{{ t('admin.overview.auditMissingOperationId') }}: {{ stats?.usage_audit?.usage_without_operation ?? 0 }}</div>
        <div>{{ t('admin.overview.auditMissingProjectId') }}: {{ stats?.usage_audit?.usage_without_project ?? 0 }}</div>
        <div>{{ t('admin.overview.auditMissingOperationRecord') }}: {{ stats?.usage_audit?.usage_with_missing_operation_record ?? 0 }}</div>
        <div>{{ t('admin.overview.auditMissingProjectRecord') }}: {{ stats?.usage_audit?.usage_with_missing_project_record ?? 0 }}</div>
        <div>{{ t('admin.overview.auditProjectUserMismatch') }}: {{ stats?.usage_audit?.usage_with_project_user_mismatch ?? 0 }}</div>
        <div>{{ t('admin.overview.auditOperationUserMismatch') }}: {{ stats?.usage_audit?.usage_with_operation_user_mismatch ?? 0 }}</div>
        <div>{{ t('admin.overview.auditOperationValueMismatch') }}: {{ stats?.usage_audit?.usage_operation_value_mismatch ?? 0 }}</div>
        <div>{{ t('admin.overview.auditNegativeBalanceUsers') }}: {{ stats?.usage_audit?.negative_balance_users ?? 0 }}</div>
      </div>
    </Card>
  </div>
</template>
