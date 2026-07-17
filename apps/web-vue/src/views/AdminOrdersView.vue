<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AdminOrdersTab from '@/components/admin/AdminOrdersTab.vue'
import { getAdminOrders } from '@/api/admin'
import type { PaymentOrderListResponse } from '@/types'

type OrderStatusFilter = '' | 'PENDING' | 'PAID' | 'CANCELLED' | 'REFUNDED' | 'EXPIRED'

const { t } = useI18n()

const page = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const ordersData = ref<PaymentOrderListResponse | null>(null)
const orderFilters = ref<{ search: string; status: OrderStatusFilter }>({
  search: '',
  status: '',
})

function orderStatusChipClass(value: string) {
  const status = (value || '').toUpperCase()
  if (status === 'PAID' || status === 'SUCCESS') {
    return 'border-emerald-300/70 bg-emerald-100 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  if (status === 'PENDING' || status === 'UNPAID') {
    return 'border-amber-300/80 bg-amber-100 text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (status === 'FAILED' || status === 'CANCELLED' || status === 'CLOSED' || status === 'EXPIRED' || status === 'REFUNDED') {
    return 'border-red-300/80 bg-red-100 text-red-700 dark:border-red-700/50 dark:bg-red-900/20 dark:text-red-300'
  }
  return 'border-stone-300 bg-stone-100 text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function formatCurrency(value?: number, digits = 6): string {
  return Number(value || 0).toFixed(digits)
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null) {
    const maybe = err as { response?: { data?: { detail?: string } }; message?: string }
    return maybe.response?.data?.detail || maybe.message || fallback
  }
  return fallback
}

function buildOrderFilters() {
  return {
    ...(orderFilters.value.search.trim() ? { search: orderFilters.value.search.trim() } : {}),
    ...(orderFilters.value.status ? { status: orderFilters.value.status } : {}),
    type: 'RECHARGE',
  }
}

async function loadOrders() {
  loading.value = true
  error.value = ''
  try {
    ordersData.value = await getAdminOrders(page.value, pageSize, buildOrderFilters())
  } catch (e: unknown) {
    error.value = getErrorMessage(e, t('admin.orders.loadFailed'))
    ordersData.value = null
  } finally {
    loading.value = false
  }
}

async function applyOrderFilters() {
  page.value = 1
  await loadOrders()
}

async function resetOrderFilters() {
  orderFilters.value = { search: '', status: '' }
  page.value = 1
  await loadOrders()
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadOrders()
  }
}

function nextPage() {
  if (ordersData.value && page.value * pageSize < ordersData.value.total) {
    page.value++
    loadOrders()
  }
}

onMounted(loadOrders)
</script>

<template>
  <AdminLayout>
    <AdminOrdersTab
      :orders-data="ordersData"
      :loading="loading"
      :error="error"
      :filters="orderFilters"
      :page="page"
      :page-size="pageSize"
      :order-status-chip-class="orderStatusChipClass"
      :format-currency="formatCurrency"
      :format-date-time="formatDateTime"
      @refresh="loadOrders"
      @apply-filters="applyOrderFilters"
      @reset-filters="resetOrderFilters"
      @prev-page="prevPage"
      @next-page="nextPage"
      @update:filters="orderFilters = $event"
    />
  </AdminLayout>
</template>