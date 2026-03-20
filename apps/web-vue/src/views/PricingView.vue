<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getBalance, getPricing } from '@/api/billing'
import { useAuthStore } from '@/stores/auth'
import type { PricingRule } from '@/types'
import { Wallet, ArrowUpRight, Receipt, Coins } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const rules = ref<PricingRule[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)

function formatUsd(value: number): string {
  return `$${Number(value || 0).toFixed(6)}`
}

function formatUsd2(value: number): string {
  return `$${Number(value || 0).toFixed(2)}`
}

function formatRule(rule: PricingRule): string {
  if (rule.billing_mode === 'REQUEST') {
    return `${formatUsd(rule.request_price)} / request`
  }
  return `${formatUsd(rule.input_price)} input + ${formatUsd(rule.output_price)} output / ${rule.token_unit.toLocaleString()} tokens`
}

async function loadPricingPage() {
  loading.value = true
  loadError.value = null
  try {
    const tasks: Promise<any>[] = [getPricing()]
    if (authStore.isAuthenticated) {
      tasks.push(getBalance())
    }
    const [pricing, balanceData] = await Promise.all(tasks)
    rules.value = pricing || []

    if (balanceData) {
      balance.value = balanceData.balance || 0
      dailyUsage.value = balanceData.daily_usage || 0
      monthlyUsage.value = balanceData.monthly_usage || 0
      authStore.setBalance(balance.value)
    }
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || 'Failed to load pricing'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadPricingPage()
})
</script>

<template>
  <AppLayout>
    <div class="muse-page-shell muse-page-shell-wide">
      <section class="muse-page-header">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Pricing</h1>
            <p class="mt-1 text-sm text-stone-600 dark:text-zinc-400">Models are billed per token or per request. Recharge before use.</p>
          </div>
          <Button v-if="authStore.isAuthenticated" variant="secondary" @click="loadPricingPage">Refresh</Button>
        </div>
      </section>

      <div v-if="authStore.isAuthenticated" class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card class="border-amber-400/50">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm text-stone-600 dark:text-zinc-400">Current Balance</p>
              <p class="mt-1 text-2xl font-bold text-stone-900 dark:text-stone-100">{{ formatUsd2(balance) }}</p>
              <p class="mt-2 text-xs text-stone-600 dark:text-zinc-400">
                Today: {{ formatUsd2(dailyUsage) }} · This month: {{ formatUsd2(monthlyUsage) }}
              </p>
            </div>
            <div class="rounded-md bg-amber-500/15 p-2 text-amber-700 dark:text-amber-300">
              <Wallet class="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card>
          <div class="flex h-full items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-stone-900 dark:text-stone-100">Recharge Entry</p>
              <p class="mt-1 text-xs text-stone-600 dark:text-zinc-400">Jump directly to recharge when balance is low.</p>
            </div>
            <Button variant="primary" @click="router.push('/recharge')">
              <ArrowUpRight class="h-4 w-4" />
              Recharge
            </Button>
          </div>
        </Card>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
      </div>

      <div v-else-if="loadError" class="rounded-md border border-red-400/40 bg-red-100/50 p-4 text-sm text-red-700 dark:border-red-700/60 dark:bg-red-900/20 dark:text-red-300">
        {{ loadError }}
      </div>

      <div v-else-if="rules.length === 0" class="rounded-md border border-stone-300/90 bg-stone-100/70 p-8 sm:p-10 text-center text-sm text-stone-600 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-400">
        No pricing rules are available yet.
      </div>

      <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card
          v-for="rule in rules"
          :key="rule.id"
          class="space-y-3"
          :class="rule.is_active === false ? 'opacity-70' : ''"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-base font-semibold text-stone-900 break-all dark:text-stone-100">{{ rule.model }}</h3>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-medium"
              :class="
                rule.billing_mode === 'TOKEN'
                  ? 'bg-stone-900/10 text-stone-700 dark:bg-zinc-700/40 dark:text-zinc-200'
                  : 'bg-amber-500/20 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300'
              "
            >
              {{ rule.billing_mode }}
            </span>
          </div>

          <p class="text-sm text-stone-700 dark:text-zinc-300">
            {{ formatRule(rule) }}
          </p>

          <div class="flex items-center justify-between text-xs text-stone-600 dark:text-zinc-400">
            <span class="inline-flex items-center gap-1">
              <Receipt class="h-3.5 w-3.5" />
              {{ rule.billing_mode === 'TOKEN' ? 'Billed by input/output tokens' : 'Fixed price per request' }}
            </span>
            <span class="inline-flex items-center gap-1">
              <Coins class="h-3.5 w-3.5" />
              {{ rule.is_active === false ? 'Disabled' : 'Active' }}
            </span>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
