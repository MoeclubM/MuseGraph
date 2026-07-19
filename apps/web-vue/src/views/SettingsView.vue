<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getBalance } from '@/api/billing'
import { getUserUsage } from '@/api/users'
import { getMyUsageDetails } from '@/api/usage'
import UsageRecordsTable from '@/components/usage/UsageRecordsTable.vue'
import type { UsageRecordListResponse } from '@/types'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { CreditCard, User, Wallet, Edit3, Save, X, Lock, Key } from '@lucide/vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToast()

const loading = ref(true)
const loadError = ref<string | null>(null)
const balance = ref(0)
const dailyUsage = ref(0)
const monthlyUsage = ref(0)
const totalTokens = ref(0)
const totalCost = ref(0)
const totalRequests = ref(0)

const usageDetailsPage = ref(1)
const usageDetailsPageSize = 10
const usageDetailsLoading = ref(false)
const usageDetailsError = ref('')
const usageDetailsData = ref<UsageRecordListResponse | null>(null)
const usageDetailsModelFilter = ref('')

const isEditing = ref(false)
const editNickname = ref('')
const editEmail = ref('')
const saving = ref(false)

const isChangingPassword = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const changingPassword = ref(false)

const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || '—')

function formatUsd(value: number): string {
  return `$${Number(value || 0).toFixed(2)}`
}

function formatTokens(value: number): string {
  return Number(value || 0).toLocaleString()
}

function startEditing() {
  editNickname.value = authStore.user?.nickname || ''
  editEmail.value = authStore.user?.email || ''
  isEditing.value = true
}

function cancelEditing() {
  isEditing.value = false
  editNickname.value = ''
  editEmail.value = ''
}

async function saveProfile() {
  if (!editNickname.value.trim() || !editEmail.value.trim()) {
    toast.error(t('settings.profile.errors.required'))
    return
  }

  saving.value = true
  try {
    await authStore.updateUser({
      nickname: editNickname.value.trim(),
      email: editEmail.value.trim(),
    })
    toast.success(t('settings.profile.saved'))
    isEditing.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('settings.profile.errors.saveFailed'))
  } finally {
    saving.value = false
  }
}

function startChangingPassword() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  isChangingPassword.value = true
}

function cancelChangingPassword() {
  isChangingPassword.value = false
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
}

async function savePassword() {
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    toast.error(t('settings.password.errors.required'))
    return
  }
  
  if (newPassword.value !== confirmPassword.value) {
    toast.error(t('settings.password.errors.mismatch'))
    return
  }
  
  if (newPassword.value.length < 6) {
    toast.error(t('settings.password.errors.tooShort'))
    return
  }

  changingPassword.value = true
  try {
    await authStore.changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    toast.success(t('settings.password.saved'))
    isChangingPassword.value = false
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('settings.password.errors.saveFailed'))
  } finally {
    changingPassword.value = false
  }
}

async function loadSettings() {
  loading.value = true
  loadError.value = null
  try {
    if (!authStore.user?.id) {
      await authStore.fetchMe()
    }
    const userId = authStore.user?.id
    if (!userId) {
      throw new Error(t('settings.errors.noUser'))
    }
    const [balanceData, usageData] = await Promise.all([getBalance(), getUserUsage(userId)])
    balance.value = balanceData.balance || 0
    dailyUsage.value = balanceData.daily_usage || 0
    monthlyUsage.value = balanceData.monthly_usage || 0
    totalTokens.value = usageData.total_tokens || 0
    totalCost.value = usageData.total_cost || 0
    totalRequests.value = usageData.total_requests || 0
    authStore.setBalance(balance.value)
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || t('settings.errors.loadFailed')
  } finally {
    loading.value = false
  }
}

async function loadUsageDetails() {
  usageDetailsLoading.value = true
  usageDetailsError.value = ''
  try {
    usageDetailsData.value = await getMyUsageDetails(
      usageDetailsPage.value,
      usageDetailsPageSize,
      { model: usageDetailsModelFilter.value.trim() || undefined },
    )
  } catch (e: any) {
    usageDetailsError.value = e?.response?.data?.detail || e?.message || t('usageRecords.loadFailed')
    usageDetailsData.value = null
  } finally {
    usageDetailsLoading.value = false
  }
}

async function applyUsageDetailsFilters() {
  usageDetailsPage.value = 1
  await loadUsageDetails()
}

onMounted(() => {
  void loadSettings()
  void loadUsageDetails()
})
</script>

<template>
  <AppLayout>
    <div class="muse-page muse-page-shell muse-page-shell-standard">
      <header class="muse-page-hero">
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl muse-text-title">{{ t('settings.title') }}</h1>
          <p class="mt-2 muse-text-caption">{{ t('settings.subtitle') }}</p>
        </div>
        <Button variant="secondary" @click="router.push('/settings/prompt-templates')">
          <Key class="h-4 w-4" />Agent 提示词模板
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
          <Card>
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <User class="h-4 w-4 muse-text-muted" />
                <h2 class="text-base font-semibold muse-text-heading">{{ t('settings.profile.title') }}</h2>
              </div>
              <Button v-if="!isEditing" variant="secondary" size="sm" @click="startEditing">
                <Edit3 class="mr-1 h-4 w-4" />
                {{ t('settings.profile.edit') }}
              </Button>
            </div>

            <template v-if="!isEditing">
              <dl class="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.profile.nickname') }}</dt>
                  <dd class="mt-1 text-sm muse-text-body">{{ displayName }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.profile.email') }}</dt>
                  <dd class="mt-1 text-sm muse-text-body">{{ authStore.user?.email || '—' }}</dd>
                </div>
              </dl>
            </template>

            <template v-else>
              <div class="space-y-4">
                <div>
                  <label class="mb-1 block text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.profile.nickname') }}</label>
                  <Input v-model="editNickname" size="sm" :placeholder="t('settings.profile.nicknamePlaceholder')" />
                </div>
                <div>
                  <label class="mb-1 block text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.profile.email') }}</label>
                  <Input v-model="editEmail" type="email" size="sm" :placeholder="t('settings.profile.emailPlaceholder')" />
                </div>
                <div class="flex gap-2">
                  <Button variant="primary" size="sm" :loading="saving" @click="saveProfile">
                    <Save class="mr-1 h-4 w-4" />
                    {{ t('settings.profile.save') }}
                  </Button>
                  <Button variant="secondary" size="sm" :disabled="saving" @click="cancelEditing">
                    <X class="mr-1 h-4 w-4" />
                    {{ t('settings.profile.cancel') }}
                  </Button>
                </div>
              </div>
            </template>
          </Card>

          <Card>
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <Lock class="h-4 w-4 muse-text-muted" />
                <h2 class="text-base font-semibold muse-text-heading">{{ t('settings.password.title') }}</h2>
              </div>
              <Button v-if="!isChangingPassword" variant="secondary" size="sm" @click="startChangingPassword">
                <Key class="mr-1 h-4 w-4" />
                {{ t('settings.password.change') }}
              </Button>
            </div>
            
            <template v-if="!isChangingPassword">
              <p class="text-sm muse-text-muted">{{ t('settings.password.hint') }}</p>
            </template>
            
            <template v-else>
              <div class="space-y-4">
                <div>
                  <label class="mb-1 block text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.password.current') }}</label>
                  <Input v-model="currentPassword" type="password" size="sm" :placeholder="t('settings.password.currentPlaceholder')" />
                </div>
                <div>
                  <label class="mb-1 block text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.password.new') }}</label>
                  <Input v-model="newPassword" type="password" size="sm" :placeholder="t('settings.password.newPlaceholder')" />
                </div>
                <div>
                  <label class="mb-1 block text-xs uppercase tracking-wide muse-text-faint">{{ t('settings.password.confirm') }}</label>
                  <Input v-model="confirmPassword" type="password" size="sm" :placeholder="t('settings.password.confirmPlaceholder')" />
                </div>
                <div class="flex gap-2">
                  <Button variant="primary" size="sm" :loading="changingPassword" @click="savePassword">
                    <Save class="mr-1 h-4 w-4" />
                    {{ t('settings.password.save') }}
                  </Button>
                  <Button variant="secondary" size="sm" :disabled="changingPassword" @click="cancelChangingPassword">
                    <X class="mr-1 h-4 w-4" />
                    {{ t('settings.password.cancel') }}
                  </Button>
                </div>
              </div>
            </template>
          </Card>

          <Card>
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <Wallet class="h-4 w-4 muse-text-muted" />
                <h2 class="text-base font-semibold muse-text-heading">{{ t('settings.billing.title') }}</h2>
              </div>
              <Button variant="primary" size="sm" @click="router.push('/recharge')">
                {{ t('settings.billing.recharge') }}
              </Button>
            </div>
            <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.balance') }}</p>
                <p class="mt-1 text-xl font-bold muse-text-body">{{ formatUsd(balance) }}</p>
              </div>
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.todaySpend') }}</p>
                <p class="mt-1 text-lg font-semibold muse-text-body">{{ formatUsd(dailyUsage) }}</p>
              </div>
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.monthSpend') }}</p>
                <p class="mt-1 text-lg font-semibold muse-text-body">{{ formatUsd(monthlyUsage) }}</p>
              </div>
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.totalTokens') }}</p>
                <p class="mt-1 text-lg font-semibold muse-text-body">{{ formatTokens(totalTokens) }}</p>
              </div>
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.totalSpend') }}</p>
                <p class="mt-1 text-lg font-semibold muse-text-body">{{ formatUsd(totalCost) }}</p>
              </div>
              <div>
                <p class="text-xs muse-text-muted">{{ t('settings.billing.totalRequests') }}</p>
                <p class="mt-1 text-lg font-semibold muse-text-body">{{ totalRequests.toLocaleString() }}</p>
              </div>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" @click="router.push('/pricing')">
                <CreditCard class="h-4 w-4" />
                {{ t('settings.billing.viewPricing') }}
              </Button>
            </div>
          </Card>

          <Card>
            <h2 class="mb-1 text-base font-semibold muse-text-heading">{{ t('settings.usageDetails.title') }}</h2>
            <p class="mb-4 text-sm muse-text-muted">{{ t('settings.usageDetails.subtitle') }}</p>
            <UsageRecordsTable
              :data="usageDetailsData"
              :loading="usageDetailsLoading"
              :error="usageDetailsError"
              :page="usageDetailsPage"
              :page-size="usageDetailsPageSize"
              :model-filter="usageDetailsModelFilter"
              @update:model-filter="usageDetailsModelFilter = $event"
              @refresh="loadUsageDetails"
              @apply-filters="applyUsageDetailsFilters"
              @prev-page="usageDetailsPage--; loadUsageDetails()"
              @next-page="usageDetailsPage++; loadUsageDetails()"
            />
          </Card>
        </section>
      </template>
    </div>
  </AppLayout>
</template>
