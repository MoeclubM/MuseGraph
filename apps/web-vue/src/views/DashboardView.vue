<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
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
  Settings,
} from '@lucide/vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(true)
const loadError = ref<string | null>(null)
const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)
const totalTokens = ref(0)
const totalCost = ref(0)
const totalRequests = ref(0)

const quickActions = [
  {
    key: 'projects',
    titleKey: 'dashboard.projectsAction',
    hintKey: 'dashboard.projectsActionHint',
    icon: FolderOpen,
    to: '/projects',
  },
  {
    key: 'settings',
    titleKey: 'dashboard.settingsAction',
    hintKey: 'dashboard.settingsActionHint',
    icon: Settings,
    to: '/settings',
  },
  {
    key: 'pricing',
    titleKey: 'dashboard.pricingAction',
    hintKey: 'dashboard.pricingActionHint',
    icon: CreditCard,
    to: '/pricing',
  },
  {
    key: 'recharge',
    titleKey: 'dashboard.rechargeAction',
    hintKey: 'dashboard.rechargeActionHint',
    icon: PlusCircle,
    to: '/recharge',
  },
] as const

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
      throw new Error(t('dashboard.errors.noUser'))
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
    loadError.value = e?.response?.data?.detail || e?.message || t('dashboard.errors.loadFailed')
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
    <div class="muse-page muse-page-shell muse-page-shell-wide">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl muse-text-title">{{ t('dashboard.title') }}</h1>
          <p class="mt-2 muse-text-caption">{{ t('dashboard.subtitle') }}</p>
        </div>
        <Button variant="secondary" class="shrink-0" @click="loadDashboardStats">
          {{ t('dashboard.refresh') }}
        </Button>
      </header>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="muse-spinner" />
      </div>

      <div v-else-if="loadError" class="muse-alert-error">
        {{ loadError }}
      </div>

      <template v-else>
        <section class="muse-page-section">
          <div class="muse-stat-grid">
            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.currentBalance') }}</p>
                  <p class="mt-2 text-2xl font-bold muse-text-body">{{ formatUsd(balance) }}</p>
                </div>
                <div class="muse-stat-icon">
                  <Wallet class="h-5 w-5" />
                </div>
              </div>
            </Card>

            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.totalTokens') }}</p>
                  <p class="mt-2 text-2xl font-bold muse-text-body">{{ formatTokens(totalTokens) }}</p>
                </div>
                <div class="muse-stat-icon">
                  <Coins class="h-5 w-5" />
                </div>
              </div>
            </Card>

            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.totalSpend') }}</p>
                  <p class="mt-2 text-2xl font-bold muse-text-body">{{ formatUsd(totalCost) }}</p>
                </div>
                <div class="muse-stat-icon">
                  <ReceiptText class="h-5 w-5" />
                </div>
              </div>
            </Card>
          </div>

          <div class="muse-stat-grid">
            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.todaySpend') }}</p>
                  <p class="mt-2 text-xl font-semibold muse-text-body">{{ formatUsd(dailyUsage) }}</p>
                </div>
                <CalendarDays class="h-5 w-5 shrink-0 muse-text-muted" />
              </div>
            </Card>

            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.monthSpend') }}</p>
                  <p class="mt-2 text-xl font-semibold muse-text-body">{{ formatUsd(monthlyUsage) }}</p>
                </div>
                <CalendarDays class="h-5 w-5 shrink-0 muse-text-muted" />
              </div>
            </Card>

            <Card variant="stat">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="text-sm muse-text-muted">{{ t('dashboard.totalRequests') }}</p>
                  <p class="mt-2 text-xl font-semibold muse-text-body">{{ totalRequests.toLocaleString() }}</p>
                </div>
                <ReceiptText class="h-5 w-5 shrink-0 muse-text-muted" />
              </div>
            </Card>
          </div>
        </section>

        <section class="muse-page-section muse-page-section-loose">
          <h2 class="text-base font-semibold muse-text-heading">{{ t('dashboard.quickActions') }}</h2>
          <div class="muse-quick-action-grid">
            <button
              v-for="action in quickActions"
              :key="action.key"
              type="button"
              class="muse-card-interactive"
              @click="router.push(action.to)"
            >
              <div class="min-w-0">
                <p class="text-sm font-medium muse-text-body">{{ t(action.titleKey) }}</p>
                <p class="mt-1 text-xs leading-relaxed muse-text-muted">{{ t(action.hintKey) }}</p>
              </div>
              <component :is="action.icon" class="h-4 w-4 shrink-0 muse-text-muted" />
            </button>
          </div>
        </section>
      </template>
    </div>
  </AppLayout>
</template>
