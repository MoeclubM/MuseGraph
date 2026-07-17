<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { PaymentOrderListResponse } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'

type OrderStatusFilter = '' | 'PENDING' | 'PAID' | 'CANCELLED' | 'REFUNDED' | 'EXPIRED'

interface OrderFilters {
  search: string
  status: OrderStatusFilter
}

const props = defineProps<{
  ordersData: PaymentOrderListResponse | null
  loading: boolean
  error: string
  filters: OrderFilters
  page: number
  pageSize: number
  orderStatusChipClass: (value: string) => string
  formatCurrency: (value?: number, digits?: number) => string
  formatDateTime: (value?: string | null) => string
}>()

const emit = defineEmits<{
  refresh: []
  'apply-filters': []
  'reset-filters': []
  'prev-page': []
  'next-page': []
  'update:filters': [value: OrderFilters]
}>()

const { t } = useI18n()

function updateSearch(value: string | number) {
  emit('update:filters', { ...props.filters, search: String(value) })
}

function updateStatus(value: unknown) {
  emit('update:filters', { ...props.filters, status: String(value || '') as OrderStatusFilter })
}

function userLabel(email?: string | null, nickname?: string | null) {
  if (nickname && email) return `${nickname} · ${email}`
  return nickname || email || '—'
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <div class="space-y-0.5">
        <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">{{ t('admin.orders.title') }}</h2>
        <p class="text-xs text-stone-500 dark:text-zinc-400">
          {{ t('admin.orders.subtitle', { count: ordersData?.total ?? 0 }) }}
        </p>
      </div>
      <Button size="sm" variant="secondary" :disabled="loading" @click="emit('refresh')">
        {{ t('admin.orders.refresh') }}
      </Button>
    </div>

    <Card class="space-y-3">
      <div class="grid gap-2 md:grid-cols-2">
        <Input
          :model-value="filters.search"
          size="sm"
          :placeholder="t('admin.orders.searchPlaceholder')"
          @update:model-value="updateSearch"
          @keyup.enter="emit('apply-filters')"
        />
        <Select :model-value="filters.status" size="sm" @update:model-value="updateStatus">
          <option value="">{{ t('admin.common.allStatus') }}</option>
          <option value="PENDING">PENDING</option>
          <option value="PAID">PAID</option>
          <option value="CANCELLED">CANCELLED</option>
          <option value="REFUNDED">REFUNDED</option>
          <option value="EXPIRED">EXPIRED</option>
        </Select>
      </div>
      <div class="flex justify-end gap-2">
        <Button size="sm" variant="secondary" @click="emit('reset-filters')">{{ t('admin.common.reset') }}</Button>
        <Button size="sm" @click="emit('apply-filters')">{{ t('admin.common.search') }}</Button>
      </div>
    </Card>

    <Alert v-if="error" variant="destructive">{{ error }}</Alert>

    <Card :stack="false">
      <div v-if="loading" class="p-4 text-sm text-stone-500 dark:text-zinc-400">
        {{ t('admin.orders.loading') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
            <tr class="border-b border-stone-300 dark:border-zinc-700">
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.orderNo') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.orders.user') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.amount') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.status') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.method') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('admin.orders.adapter') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.created') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('common.paid') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="order in ordersData?.orders ?? []"
              :key="order.id || order.order_no"
              class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
            >
              <td class="px-3 py-2 font-mono text-stone-700 dark:text-zinc-200">{{ order.order_no }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">
                {{ userLabel(order.user_email, order.user_nickname) }}
              </td>
              <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">${{ formatCurrency(order.amount, 2) }}</td>
              <td class="px-3 py-2">
                <span :class="['inline-flex rounded-full border px-2 py-0.5 text-xs font-medium', orderStatusChipClass(order.status)]">
                  {{ order.status }}
                </span>
              </td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ order.payment_method || '—' }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ order.payment_adapter_name || '—' }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.created_at) }}</td>
              <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.paid_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!ordersData?.orders?.length" class="p-4 text-sm text-stone-500 dark:text-zinc-400">
          {{ t('admin.orders.empty') }}
        </p>
      </div>
      <div class="mt-4 flex items-center justify-end gap-2 border-t border-stone-300/80 pt-4 dark:border-zinc-700/60">
        <Button size="sm" variant="secondary" :disabled="page <= 1 || loading" @click="emit('prev-page')">
          {{ t('admin.common.prev') }}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          :disabled="loading || !ordersData || page * pageSize >= ordersData.total"
          @click="emit('next-page')"
        >
          {{ t('admin.common.next') }}
        </Button>
      </div>
    </Card>
  </div>
</template>