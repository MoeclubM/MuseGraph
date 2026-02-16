<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getBalance, deposit } from '@/api/billing'
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

const presetAmounts = [10, 20, 50, 100, 200, 500]

const paymentMethods = [
  { value: 'alipay', label: 'Alipay', icon: CreditCard },
  { value: 'wechat', label: 'WeChat Pay', icon: Banknote },
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
    await deposit(numAmount, paymentMethod.value)
    success.value = true
    amount.value = ''
    await loadBalance()
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || 'Deposit failed'
  } finally {
    loading.value = false
  }
}

function selectPreset(val: number) {
  amount.value = val.toString()
}

onMounted(loadBalance)
</script>

<template>
  <AppLayout>
    <div class="p-6 max-w-2xl mx-auto">
      <div class="mb-6">
        <h1 class="text-2xl font-bold text-white">Recharge</h1>
        <p class="text-sm text-slate-400 mt-1">Top up your account balance</p>
      </div>

      <!-- Balance Card -->
      <Card class="mb-6">
        <div class="flex items-center gap-4">
          <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600/20">
            <Wallet class="w-6 h-6 text-blue-400" />
          </div>
          <div class="flex-1">
            <p class="text-sm text-slate-400">Current Balance</p>
            <p v-if="balanceLoading" class="text-2xl font-bold text-white">--</p>
            <p v-else class="text-2xl font-bold text-white">${{ balance.toFixed(2) }}</p>
          </div>
          <div class="text-right space-y-1">
            <p class="text-xs text-slate-500">
              Today: <span class="text-slate-300">{{ dailyUsage }} ops</span>
            </p>
            <p class="text-xs text-slate-500">
              This month: <span class="text-slate-300">{{ monthlyUsage }} ops</span>
            </p>
          </div>
        </div>
      </Card>

      <!-- Recharge Form -->
      <Card>
        <h2 class="text-base font-semibold text-slate-200 mb-4">Add Funds</h2>

        <div v-if="success" class="mb-4 flex items-center gap-2 rounded-lg bg-emerald-900/30 border border-emerald-800 px-4 py-3 text-sm text-emerald-300">
          <CheckCircle class="w-4 h-4" />
          Deposit successful! Your balance has been updated.
        </div>

        <div v-if="error" class="mb-4 rounded-lg bg-red-900/30 border border-red-800 px-4 py-3 text-sm text-red-300">
          {{ error }}
        </div>

        <!-- Preset Amounts -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-slate-300 mb-2">Quick Select</label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="preset in presetAmounts"
              :key="preset"
              class="rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors"
              :class="
                amount === preset.toString()
                  ? 'border-blue-500 bg-blue-600/20 text-blue-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'
              "
              @click="selectPreset(preset)"
            >
              ${{ preset }}
            </button>
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
          <label class="block text-sm font-medium text-slate-300 mb-2">Payment Method</label>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="method in paymentMethods"
              :key="method.value"
              class="flex items-center gap-2 rounded-lg border px-4 py-3 text-sm transition-colors"
              :class="
                paymentMethod === method.value
                  ? 'border-blue-500 bg-blue-600/20 text-blue-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'
              "
              @click="paymentMethod = method.value"
            >
              <component :is="method.icon" class="w-4 h-4" />
              {{ method.label }}
            </button>
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
    </div>
  </AppLayout>
</template>
