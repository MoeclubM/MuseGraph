<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { getBalance, getPricing } from '@/api/billing'
import { useAuthStore } from '@/stores/auth'
import type { PricingRule } from '@/types'
import { Wallet, ArrowUpRight, Receipt, Coins } from '@lucide/vue'

const router = useRouter()
const { t } = useI18n()
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
    return `${formatUsd(rule.request_price)}${t('pricing.perRequest')}`
  }
  return t('pricing.tokenBilling', {
    input: formatUsd(rule.input_price),
    output: formatUsd(rule.output_price),
    unit: rule.token_unit.toLocaleString(),
  })
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
    loadError.value = e?.response?.data?.detail || e?.message || t('pricing.errors.loadFailed')
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
    <div class="muse-page muse-page-shell muse-page-shell-wide">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl muse-text-title">{{ t('pricing.title') }}</h1>
          <p class="mt-2 muse-text-caption">{{ t('pricing.subtitle') }}</p>
        </div>
      </header>

      <div v-if="authStore.isAuthenticated" class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm muse-text-muted">{{ t('pricing.currentBalance') }}</p>
              <p class="mt-1 text-2xl font-bold muse-text-body">{{ formatUsd2(balance) }}</p>
              <p class="mt-2 text-xs muse-text-muted">
                {{ t('pricing.todayMonth', { today: formatUsd2(dailyUsage), month: formatUsd2(monthlyUsage) }) }}
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
              <p class="text-sm font-medium muse-text-body">{{ t('pricing.rechargeEntry') }}</p>
              <p class="mt-1 text-xs muse-text-muted">{{ t('pricing.rechargeHint') }}</p>
            </div>
            <Button variant="primary" @click="router.push('/recharge')">
              <ArrowUpRight class="h-4 w-4" />
              {{ t('pricing.recharge') }}
            </Button>
          </div>
        </Card>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="muse-spinner" />
      </div>

      <div v-else-if="loadError" class="muse-alert-error">
        {{ loadError }}
      </div>

      <div v-else-if="rules.length === 0" class="muse-card muse-card-inset muse-card-padded p-8 sm:p-10 text-center text-sm muse-text-muted">
        {{ t('pricing.noRules') }}
      </div>

      <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card
          v-for="rule in rules"
          :key="rule.id"
          class="space-y-3"
          :class="rule.is_active === false ? 'opacity-70' : ''"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-base font-semibold break-all muse-text-body">{{ rule.model }}</h3>
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

          <p class="text-sm muse-text-body">
            {{ formatRule(rule) }}
          </p>

          <div class="flex items-center justify-between text-xs muse-text-muted">
            <span class="inline-flex items-center gap-1">
              <Receipt class="h-3.5 w-3.5" />
              {{ rule.billing_mode === 'TOKEN' ? t('pricing.billedByToken') : t('pricing.billedByRequest') }}
            </span>
            <span class="inline-flex items-center gap-1">
              <Coins class="h-3.5 w-3.5" />
              {{ rule.is_active === false ? t('pricing.disabled') : t('pricing.active') }}
            </span>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>
