<script setup lang="ts">
import type { StatsResponse } from '@/types'
import Card from '@/components/ui/Card.vue'

defineProps<{
  stats: StatsResponse | null
  formatCurrency: (value?: number, digits?: number) => string
  formatTokens: (value?: number) => string
}>()
</script>

<template>
  <div class="space-y-4">
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Users</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_users ?? 0 }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Projects</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_projects ?? 0 }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Operations</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_operations ?? 0 }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Revenue</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_revenue, 2) }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Usage Cost</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_usage_cost) }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Total Tokens</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatTokens(stats?.total_tokens) }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">24h Tokens</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatTokens(stats?.last_24h_tokens) }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Total Balance</p>
        <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_balance) }}</p>
      </Card>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">24h Requests</p>
        <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.last_24h_request_count ?? 0 }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">7d Cost</p>
        <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.last_7d_cost) }}</p>
      </Card>
      <Card class="space-y-1">
        <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">30d Cost</p>
        <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.last_30d_cost) }}</p>
      </Card>
    </div>

    <div class="grid gap-3 md:grid-cols-2">
      <Card :padding="false">
        <div class="border-b border-stone-300/80 px-3 py-3 sm:px-4 dark:border-zinc-700/60">
          <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Top Users By Cost</p>
        </div>
        <div class="py-3 sm:py-4">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                <tr class="border-b border-stone-300 dark:border-zinc-700">
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">User</th>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Req</th>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Tokens</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Cost</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="u in stats?.top_users ?? []"
                  :key="u.user_id"
                  class="border-b border-stone-200/80 dark:border-zinc-800"
                >
                  <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">
                    <p class="max-w-[220px] truncate">{{ u.nickname || u.email }}</p>
                    <p class="max-w-[220px] truncate text-xs text-stone-500 dark:text-zinc-400">{{ u.email }}</p>
                  </td>
                  <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ u.request_count }}</td>
                  <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatTokens(u.total_tokens) }}</td>
                  <td class="px-3 py-2 text-right text-stone-700 dark:text-zinc-100">{{ formatCurrency(u.cost) }}</td>
                </tr>
                <tr v-if="!(stats?.top_users?.length)">
                  <td colspan="4" class="px-3 py-3 text-center text-xs text-stone-500 dark:text-zinc-400">No usage data</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      <Card :padding="false">
        <div class="border-b border-stone-300/80 px-3 py-3 sm:px-4 dark:border-zinc-700/60">
          <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Top Models By Cost</p>
        </div>
        <div class="py-3 sm:py-4">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                <tr class="border-b border-stone-300 dark:border-zinc-700">
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Model</th>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Req</th>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Tokens</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Cost</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in stats?.top_models ?? []"
                  :key="m.model"
                  class="border-b border-stone-200/80 dark:border-zinc-800"
                >
                  <td class="px-3 py-2 font-mono text-xs text-stone-700 dark:text-zinc-200">{{ m.model }}</td>
                  <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ m.request_count }}</td>
                  <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatTokens(m.total_tokens) }}</td>
                  <td class="px-3 py-2 text-right text-stone-700 dark:text-zinc-100">{{ formatCurrency(m.cost) }}</td>
                </tr>
                <tr v-if="!(stats?.top_models?.length)">
                  <td colspan="4" class="px-3 py-3 text-center text-xs text-stone-500 dark:text-zinc-400">No model data</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </Card>
    </div>

    <Card class="space-y-2">
      <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Usage Audit</p>
      <div class="grid gap-2 text-xs text-stone-600 md:grid-cols-2 dark:text-zinc-300">
        <div>Missing operation id: {{ stats?.usage_audit?.usage_without_operation ?? 0 }}</div>
        <div>Missing project id: {{ stats?.usage_audit?.usage_without_project ?? 0 }}</div>
        <div>Missing operation record: {{ stats?.usage_audit?.usage_with_missing_operation_record ?? 0 }}</div>
        <div>Missing project record: {{ stats?.usage_audit?.usage_with_missing_project_record ?? 0 }}</div>
        <div>Project user mismatch: {{ stats?.usage_audit?.usage_with_project_user_mismatch ?? 0 }}</div>
        <div>Operation user mismatch: {{ stats?.usage_audit?.usage_with_operation_user_mismatch ?? 0 }}</div>
        <div>Operation value mismatch: {{ stats?.usage_audit?.usage_operation_value_mismatch ?? 0 }}</div>
        <div>Negative balance users: {{ stats?.usage_audit?.negative_balance_users ?? 0 }}</div>
      </div>
    </Card>
  </div>
</template>
