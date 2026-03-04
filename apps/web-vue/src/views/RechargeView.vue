<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getBalance, deposit, getPaymentOrders } from '@/api/billing'
import type { PaymentOrder } from '@/types'
import { Wallet, CreditCard, Banknote, CheckCircle } from 'lucide-vue-next'

const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)
const amount = ref('')
const paymentMethod = ref('alipay')
const loading = ref(false)
const balanceLoading = ref(true)
const success = ref(false)
const error = ref<string | null>(null)
const orders = ref<PaymentOrder[]>([])
const ordersLoading = ref(false)
const ordersError = ref<string | null>(null)

const presetAmounts = [10, 20, 50, 100, 200, 500]

const paymentMethods = [
  { value: 'alipay', label: 'Alipay', icon: CreditCard },
  { value: 'wxpay', label: 'WeChat Pay', icon: Banknote },
]

async function loadBalance() {
  balanceLoading.value = true
  try {
    const data = await getBalance()
    balance.value = data.balance
    dailyUsage.value = data.daily_usage
    monthlyUsage.value = data.monthly_usage
  } catch {
    // handle error
  } finally {
    balanceLoading.value = false
  }
}

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = null
  try {
    const data = await getPaymentOrders(1, 20)
    orders.value = data.orders || []
  } catch {
    ordersError.value = 'Failed to load recharge orders'
    orders.value = []
  } finally {
    ordersLoading.value = false
  }
}

async function handleDeposit() {
  const numAmount = parseFloat(amount.value)
  if (!numAmount || numAmount <= 0) {
    error.value = 'Please enter a valid amount'
    return
  }
  loading.value = true
  error.value = null
  success.value = false
  try {
    const order = await deposit(numAmount, paymentMethod.value)
    if (order?.payment_url) {
      window.location.href = order.payment_url
      return
    }
    success.value = true
    amount.value = ''
    await Promise.all([loadBalance(), loadOrders()])
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || 'Deposit failed'
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
  await Promise.all([loadBalance(), loadOrders()])
})
</script>

<template>
  <AppLayout>
    <div class="mx-auto w-full max-w-2xl space-y-5">
      <div>
        <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Recharge</h1>
        <p class="mt-1 text-sm text-stone-600 dark:text-zinc-400">Top up your account balance</p>
      </div>

      <!-- Balance Card -->
      <Card>
        <div class="flex items-center gap-4">
          <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/15 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
            <Wallet class="w-6 h-6" />
          </div>
          <div class="flex-1">
            <p class="text-sm text-stone-600 dark:text-zinc-400">Current Balance</p>
            <p v-if="balanceLoading" class="text-2xl font-bold text-stone-900 dark:text-stone-100">--</p>
            <p v-else class="text-2xl font-bold text-stone-900 dark:text-stone-100">${{ balance.toFixed(2) }}</p>
          </div>
          <div class="text-right space-y-1">
            <p class="text-xs text-stone-500 dark:text-zinc-400">
              Today: <span class="text-stone-700 dark:text-zinc-200">{{ dailyUsage }} ops</span>
            </p>
            <p class="text-xs text-stone-500 dark:text-zinc-400">
              This month: <span class="text-stone-700 dark:text-zinc-200">{{ monthlyUsage }} ops</span>
            </p>
          </div>
        </div>
      </Card>

      <!-- Recharge Form -->
      <Card>
        <h2 class="mb-4 text-base font-semibold text-stone-900 dark:text-stone-100">Add Funds</h2>

        <div v-if="success" class="mb-4 flex items-center gap-2 rounded-lg border border-emerald-300/70 bg-emerald-100 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300">
          <CheckCircle class="w-4 h-4" />
          Deposit successful! Your balance has been updated.
        </div>

        <div v-if="error" class="mb-4 rounded-lg border border-red-300/80 bg-red-100 px-4 py-3 text-sm text-red-700 dark:border-red-700/60 dark:bg-red-900/20 dark:text-red-300">
          {{ error }}
        </div>

        <!-- Preset Amounts -->
        <div class="mb-4">
          <label class="mb-2 block text-sm font-medium text-stone-700 dark:text-zinc-300">Quick Select</label>
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

        <!-- Custom Amount -->
        <div class="mb-4">
          <Input
            v-model="amount"
            label="Custom Amount ($)"
            type="number"
            placeholder="Enter amount"
          />
        </div>

        <!-- Payment Method -->
        <div class="mb-6">
          <label class="mb-2 block text-sm font-medium text-stone-700 dark:text-zinc-300">Payment Method</label>
          <div class="grid grid-cols-2 gap-2">
            <Button
              v-for="method in paymentMethods"
              :key="method.value"
              :variant="paymentMethod === method.value ? 'primary' : 'secondary'"
              class="h-auto w-full justify-start px-4 py-3 text-sm"
              @click="paymentMethod = method.value"
            >
              <component :is="method.icon" class="w-4 h-4" />
              {{ method.label }}
            </Button>
          </div>
        </div>

        <Button
          variant="primary"
          size="lg"
          class="w-full"
          :loading="loading"
          :disabled="!amount || parseFloat(amount) <= 0"
          @click="handleDeposit"
        >
          <Wallet class="w-4 h-4" />
          Deposit ${{ amount || '0' }}
        </Button>
      </Card>

      <Card class="mt-6">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-base font-semibold text-stone-900 dark:text-stone-100">Recharge Orders</h2>
          <Button size="sm" variant="secondary" :loading="ordersLoading" @click="loadOrders">
            Refresh
          </Button>
        </div>

        <div v-if="ordersError" class="mb-3 rounded-lg border border-red-300/80 bg-red-100 px-4 py-3 text-sm text-red-700 dark:border-red-700/60 dark:bg-red-900/20 dark:text-red-300">
          {{ ordersError }}
        </div>

        <div v-if="ordersLoading" class="text-sm text-stone-600 dark:text-zinc-400">Loading orders...</div>

        <div v-else-if="orders.length" class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-stone-300/80 text-left text-xs uppercase tracking-wide text-stone-500 dark:border-zinc-700 dark:text-zinc-400">
                <th class="px-2 py-2">Order No</th>
                <th class="px-2 py-2">Amount</th>
                <th class="px-2 py-2">Status</th>
                <th class="px-2 py-2">Method</th>
                <th class="px-2 py-2">Created</th>
                <th class="px-2 py-2">Paid</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="order in orders" :key="order.order_no" class="border-b border-stone-200/80 text-stone-700 dark:border-zinc-800/70 dark:text-zinc-300">
                <td class="px-2 py-2 font-mono text-xs">{{ order.order_no }}</td>
                <td class="px-2 py-2">${{ Number(order.amount || 0).toFixed(2) }}</td>
                <td class="px-2 py-2">
                  <span :class="orderStatusClass(order.status)">{{ order.status }}</span>
                </td>
                <td class="px-2 py-2">{{ order.payment_method || '—' }}</td>
                <td class="px-2 py-2">{{ formatDateTime(order.created_at) }}</td>
                <td class="px-2 py-2">{{ formatDateTime(order.paid_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-else class="text-sm text-stone-500 dark:text-zinc-400">No recharge orders yet.</p>
      </Card>
    </div>
  </AppLayout>
</template>
