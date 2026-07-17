<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getBalance, deposit, getPaymentOrders, getPaymentMethods } from '@/api/billing'
import type { PaymentOrder, PublicPaymentAdapter } from '@/types'
import { Wallet, CreditCard, Banknote, CheckCircle } from '@lucide/vue'

const { t } = useI18n()

const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)
const amount = ref('')
const paymentAdapters = ref<PublicPaymentAdapter[]>([])
const selectedAdapterId = ref('')
const selectedChannel = ref('')
const loading = ref(false)
const balanceLoading = ref(true)
const methodsLoading = ref(true)
const success = ref(false)
const error = ref<string | null>(null)
const orders = ref<PaymentOrder[]>([])
const ordersLoading = ref(false)
const ordersError = ref<string | null>(null)

const presetAmounts = [10, 20, 50, 100, 200, 500]

const channelIcon = (channelId: string) => {
  if (channelId === 'wxpay') return Banknote
  return CreditCard
}

const channelLabel = (channelId: string) => {
  const key = `recharge.payment.${channelId}`
  const translated = t(key)
  return translated !== key ? translated : channelId
}

const paymentOptions = computed(() => {
  const options: {
    adapterId: string
    adapterName: string
    channelId: string
    label: string
    icon: typeof CreditCard
  }[] = []
  for (const adapter of paymentAdapters.value) {
    for (const ch of adapter.channels || []) {
      options.push({
        adapterId: adapter.id,
        adapterName: adapter.display_name,
        channelId: ch.id,
        label: `${adapter.display_name} · ${channelLabel(ch.id)}`,
        icon: channelIcon(ch.id),
      })
    }
  }
  return options
})

const hasPaymentMethods = computed(() => paymentOptions.value.length > 0)

const selectedOptionKey = computed({
  get: () => (selectedAdapterId.value && selectedChannel.value
    ? `${selectedAdapterId.value}:${selectedChannel.value}`
    : ''),
  set: (value: string) => {
    const [adapterId, channelId] = value.split(':')
    selectedAdapterId.value = adapterId || ''
    selectedChannel.value = channelId || ''
  },
})

async function loadBalance() {
  balanceLoading.value = true
  try {
    const data = await getBalance()
    balance.value = data.balance
    dailyUsage.value = data.daily_usage
    monthlyUsage.value = data.monthly_usage
  } catch {
    // handled by interceptor
  } finally {
    balanceLoading.value = false
  }
}

async function loadPaymentMethods() {
  methodsLoading.value = true
  try {
    const data = await getPaymentMethods()
    paymentAdapters.value = data.adapters || []
    const first = paymentOptions.value[0]
    if (first) {
      selectedAdapterId.value = first.adapterId
      selectedChannel.value = first.channelId
    } else {
      selectedAdapterId.value = ''
      selectedChannel.value = ''
    }
  } catch {
    paymentAdapters.value = []
    selectedAdapterId.value = ''
    selectedChannel.value = ''
  } finally {
    methodsLoading.value = false
  }
}

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = null
  try {
    const data = await getPaymentOrders(1, 20)
    orders.value = data.orders || []
  } catch {
    ordersError.value = t('recharge.errors.loadOrdersFailed')
    orders.value = []
  } finally {
    ordersLoading.value = false
  }
}

async function handleDeposit() {
  const numAmount = parseFloat(amount.value)
  if (!numAmount || numAmount <= 0) {
    error.value = t('recharge.errors.invalidAmount')
    return
  }
  if (!selectedAdapterId.value || !selectedChannel.value) {
    error.value = t('recharge.errors.noPaymentMethod')
    return
  }
  loading.value = true
  error.value = null
  success.value = false
  try {
    const order = await deposit(numAmount, selectedAdapterId.value, selectedChannel.value)
    if (order?.payment_url) {
      window.location.href = order.payment_url
      return
    }
    success.value = true
    amount.value = ''
    await Promise.all([loadBalance(), loadOrders()])
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || t('recharge.errors.depositFailed')
  } finally {
    loading.value = false
  }
}

function selectPreset(val: number) {
  amount.value = val.toString()
}

function orderStatusClass(status: string): string {
  const value = (status || '').toUpperCase()
  if (value === 'PAID' || value === 'SUCCESS') return 'text-emerald-700 dark:text-emerald-300'
  if (value === 'PENDING' || value === 'UNPAID') return 'text-amber-700 dark:text-amber-300'
  if (value === 'FAILED' || value === 'CANCELLED') return 'text-red-700 dark:text-red-300'
  return 'text-stone-600 dark:text-zinc-300'
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

onMounted(async () => {
  await Promise.all([loadBalance(), loadOrders(), loadPaymentMethods()])
})
</script>

<template>
  <AppLayout>
    <div class="muse-page muse-page-shell muse-page-shell-narrow">
      <header class="muse-page-hero">
        <div class="min-w-0">
          <h1 class="text-2xl muse-text-title">{{ t('recharge.title') }}</h1>
          <p class="mt-2 muse-text-caption">{{ t('recharge.subtitle') }}</p>
        </div>
      </header>

      <Card>
        <div class="flex items-center gap-4">
          <div class="flex h-12 w-12 items-center justify-center rounded-md bg-amber-500/15 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
            <Wallet class="w-6 h-6" />
          </div>
          <div class="flex-1">
            <p class="text-sm muse-text-muted">{{ t('recharge.currentBalance') }}</p>
            <p v-if="balanceLoading" class="text-2xl font-bold muse-text-body">--</p>
            <p v-else class="text-2xl font-bold muse-text-body">${{ balance.toFixed(2) }}</p>
          </div>
          <div class="space-y-1 text-right">
            <p class="text-xs muse-text-muted">
              {{ t('recharge.todayOps', { count: dailyUsage }) }}
            </p>
            <p class="text-xs muse-text-muted">
              {{ t('recharge.monthOps', { count: monthlyUsage }) }}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <h2 class="mb-4 text-base font-semibold muse-text-heading">{{ t('recharge.addFunds') }}</h2>

        <div v-if="success" class="mb-4 flex items-center gap-2 rounded-md border border-emerald-300/70 bg-emerald-100 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300">
          <CheckCircle class="w-4 h-4" />
          {{ t('recharge.depositSuccess') }}
        </div>

        <div v-if="error" class="mb-4 muse-alert-error">
          {{ error }}
        </div>

        <div class="mb-4">
          <label class="mb-2 block text-sm font-medium muse-text-body">{{ t('recharge.quickSelect') }}</label>
          <div class="grid grid-cols-3 gap-2">
            <Button
              v-for="preset in presetAmounts"
              :key="preset"
              :variant="amount === preset.toString() ? 'primary' : 'secondary'"
              class="h-auto px-4 py-2.5 text-sm font-medium"
              @click="selectPreset(preset)"
            >
              ${{ preset }}
            </Button>
          </div>
        </div>

        <div class="mb-4">
          <Input
            v-model="amount"
            :label="t('recharge.customAmount')"
            type="number"
            :placeholder="t('recharge.customPlaceholder')"
          />
        </div>

        <div v-if="methodsLoading" class="mb-6 text-sm muse-text-muted">{{ t('common.loading') }}</div>

        <div v-else-if="hasPaymentMethods" class="mb-6">
          <label class="mb-2 block text-sm font-medium muse-text-body">{{ t('recharge.paymentMethod') }}</label>
          <div class="grid gap-2 sm:grid-cols-2">
            <Button
              v-for="opt in paymentOptions"
              :key="`${opt.adapterId}:${opt.channelId}`"
              :variant="selectedOptionKey === `${opt.adapterId}:${opt.channelId}` ? 'primary' : 'secondary'"
              class="h-auto w-full justify-start px-4 py-3 text-sm"
              @click="selectedOptionKey = `${opt.adapterId}:${opt.channelId}`"
            >
              <component :is="opt.icon" class="w-4 h-4" />
              {{ opt.label }}
            </Button>
          </div>
        </div>

        <p v-else class="mb-6 text-sm muse-text-muted">{{ t('recharge.noPaymentMethods') }}</p>

        <Button
          variant="primary"
          size="lg"
          class="w-full"
          :loading="loading"
          :disabled="!amount || parseFloat(amount) <= 0 || !hasPaymentMethods"
          @click="handleDeposit"
        >
          <Wallet class="w-4 h-4" />
          {{ t('recharge.deposit', { amount: amount || '0' }) }}
        </Button>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-base font-semibold muse-text-heading">{{ t('recharge.ordersTitle') }}</h2>
          <Button size="sm" variant="secondary" :loading="ordersLoading" @click="loadOrders">
            {{ t('common.refresh') }}
          </Button>
        </div>

        <div v-if="ordersError" class="mb-3 muse-alert-error">
          {{ ordersError }}
        </div>

        <div v-if="ordersLoading" class="text-sm muse-text-muted">{{ t('common.loading') }}</div>

        <div v-else-if="orders.length" class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-stone-300/80 text-left text-xs uppercase tracking-wide muse-text-faint dark:border-zinc-700">
                <th class="px-2 py-2">{{ t('recharge.columns.orderNo') }}</th>
                <th class="px-2 py-2">{{ t('recharge.columns.amount') }}</th>
                <th class="px-2 py-2">{{ t('recharge.columns.status') }}</th>
                <th class="px-2 py-2">{{ t('recharge.columns.method') }}</th>
                <th class="px-2 py-2">{{ t('recharge.columns.created') }}</th>
                <th class="px-2 py-2">{{ t('recharge.columns.paid') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="order in orders" :key="order.order_no" class="border-b border-stone-200/80 muse-text-body dark:border-zinc-800/70">
                <td class="px-2 py-2 font-mono text-xs">{{ order.order_no }}</td>
                <td class="px-2 py-2">${{ Number(order.amount || 0).toFixed(2) }}</td>
                <td class="px-2 py-2">
                  <span :class="orderStatusClass(order.status)">{{ order.status }}</span>
                </td>
                <td class="px-2 py-2">{{ order.payment_method || t('common.emptyDash') }}</td>
                <td class="px-2 py-2">{{ formatDateTime(order.created_at) }}</td>
                <td class="px-2 py-2">{{ formatDateTime(order.paid_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-else class="text-sm muse-text-muted">{{ t('recharge.noOrders') }}</p>
      </Card>
    </div>
  </AppLayout>
</template>