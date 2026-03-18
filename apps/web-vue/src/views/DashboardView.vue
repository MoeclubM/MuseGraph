<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getBalance } from '@/api/billing'
import { getUserUsage } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import {
  Wallet,
  Coins,
  ReceiptText,
  CalendarDays,
  FolderOpen,
  CreditCard,
  PlusCircle,
} from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(true)
const loadError = ref<string | null>(null)
const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)
const totalTokens = ref(0)
const totalCost = ref(0)
const totalRequests = ref(0)

function formatUsd(value: number): string {
  return `$${Number(value || 0).toFixed(2)}`
}

function formatTokens(value: number): string {
  return Number(value || 0).toLocaleString()
}

async function loadDashboardStats() {
  loading.value = true
  loadError.value = null
  try {
    if (!authStore.user?.id) {
      await authStore.fetchMe()
    }
    const userId = authStore.user?.id
    if (!userId) {
      throw new Error('Unable to load the current user')
    }

    const [balanceData, usageData] = await Promise.all([
      getBalance(),
      getUserUsage(userId),
    ])

    balance.value = balanceData.balance || 0
    dailyUsage.value = balanceData.daily_usage || 0
    monthlyUsage.value = balanceData.monthly_usage || 0

    totalTokens.value = usageData.total_tokens || 0
    totalCost.value = usageData.total_cost || 0
    totalRequests.value = usageData.total_requests || 0

    authStore.setBalance(balance.value)
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || 'Failed to load dashboard stats'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadDashboardStats()
})
</script>

<template>
  <AppLayout>
    <div class="mx-auto w-full max-w-6xl space-y-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold text-stone-900 dark:text-stone-100">Dashboard</h1>
          <p class="mt-1 text-sm text-stone-600 dark:text-zinc-400">Balance, token usage, and cost overview.</p>
        </div>
        <Button variant="secondary" @click="loadDashboardStats">Refresh</Button>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
      </div>

      <div v-else-if="loadError" class="rounded-xl border border-red-400/40 bg-red-100/50 p-4 text-sm text-red-700 dark:border-red-700/60 dark:bg-red-900/20 dark:text-red-300">
        {{ loadError }}
      </div>

      <template v-else>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card class="border-amber-400/40">
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">Current Balance</p>
                <p class="mt-1 text-2xl font-bold text-stone-900 dark:text-stone-100">{{ formatUsd(balance) }}</p>
              </div>
              <div class="rounded-lg bg-amber-500/15 p-2 text-amber-700 dark:text-amber-300">
                <Wallet class="h-5 w-5" />
              </div>
            </div>
          </Card>

          <Card>
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">Total Tokens Used</p>
                <p class="mt-1 text-2xl font-bold text-stone-900 dark:text-stone-100">{{ formatTokens(totalTokens) }}</p>
              </div>
              <div class="rounded-lg bg-stone-900/10 p-2 text-stone-700 dark:bg-zinc-700/30 dark:text-zinc-200">
                <Coins class="h-5 w-5" />
              </div>
            </div>
          </Card>

          <Card>
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">Total Spend</p>
                <p class="mt-1 text-2xl font-bold text-stone-900 dark:text-stone-100">{{ formatUsd(totalCost) }}</p>
              </div>
              <div class="rounded-lg bg-stone-900/10 p-2 text-stone-700 dark:bg-zinc-700/30 dark:text-zinc-200">
                <ReceiptText class="h-5 w-5" />
              </div>
            </div>
          </Card>
        </div>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card>
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">Today's Spend</p>
                <p class="mt-1 text-xl font-semibold text-stone-900 dark:text-stone-100">{{ formatUsd(dailyUsage) }}</p>
              </div>
              <CalendarDays class="h-5 w-5 text-stone-500 dark:text-zinc-400" />
            </div>
          </Card>

          <Card>
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">This Month's Spend</p>
                <p class="mt-1 text-xl font-semibold text-stone-900 dark:text-stone-100">{{ formatUsd(monthlyUsage) }}</p>
              </div>
              <CalendarDays class="h-5 w-5 text-stone-500 dark:text-zinc-400" />
            </div>
          </Card>

          <Card>
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-stone-600 dark:text-zinc-400">Total Requests</p>
                <p class="mt-1 text-xl font-semibold text-stone-900 dark:text-stone-100">{{ totalRequests.toLocaleString() }}</p>
              </div>
              <ReceiptText class="h-5 w-5 text-stone-500 dark:text-zinc-400" />
            </div>
          </Card>
        </div>

        <Card>
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-base font-semibold text-stone-900 dark:text-stone-100">Quick Actions</h2>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Button
              variant="secondary"
              class="h-auto w-full justify-between px-4 py-3 text-left hover:border-amber-500/60 dark:hover:border-amber-500/60"
              @click="router.push('/projects')"
            >
              <div>
                <p class="text-sm font-medium text-stone-900 dark:text-stone-100">Projects & Chapters</p>
                <p class="mt-0.5 text-xs text-stone-600 dark:text-zinc-400">Manage projects and open the writing workspace.</p>
              </div>
              <FolderOpen class="h-4 w-4 text-stone-500 dark:text-zinc-400" />
            </Button>

            <Button
              variant="secondary"
              class="h-auto w-full justify-between px-4 py-3 text-left hover:border-amber-500/60 dark:hover:border-amber-500/60"
              @click="router.push('/pricing')"
            >
              <div>
                <p class="text-sm font-medium text-stone-900 dark:text-stone-100">Model Pricing</p>
                <p class="mt-0.5 text-xs text-stone-600 dark:text-zinc-400">Review token and per-request billing rules.</p>
              </div>
              <CreditCard class="h-4 w-4 text-stone-500 dark:text-zinc-400" />
            </Button>

            <Button
              variant="secondary"
              class="h-auto w-full justify-between border-amber-500/50 bg-amber-500/10 px-4 py-3 text-left hover:bg-amber-500/20 dark:border-amber-500/50 dark:bg-amber-500/10 dark:hover:bg-amber-500/20"
              @click="router.push('/recharge')"
            >
              <div>
                <p class="text-sm font-medium text-stone-900 dark:text-stone-100">Recharge</p>
                <p class="mt-0.5 text-xs text-stone-700 dark:text-amber-200/80">Top up quickly when balance is low.</p>
              </div>
              <PlusCircle class="h-4 w-4 text-amber-700 dark:text-amber-300" />
            </Button>
          </div>
        </Card>
      </template>
    </div>
  </AppLayout>
</template>
