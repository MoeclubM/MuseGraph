<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getBalance } from '@/api/billing'
import { getUserUsage } from '@/api/users'
import { getMyUsageDetails } from '@/api/usage'
import {
  createMyProvider,
  deleteMyProvider,
  getMyProviders,
  updateMyProvider,
  type UserProviderPayload,
} from '@/api/providers'
import UsageRecordsTable from '@/components/usage/UsageRecordsTable.vue'
import type { UsageRecordListResponse, UserProvider } from '@/types'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { CreditCard, User, Wallet, Edit3, Save, X, Lock, Key, Plus, Server, Trash2 } from '@lucide/vue'

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
const providers = ref<UserProvider[]>([])
const providerSaving = ref(false)
const providerFormOpen = ref(false)
const providerForm = reactive({
  id: '',
  name: '',
  provider: 'openai_compatible',
  api_key: '',
  base_url: '',
  models: '',
  embedding_models: '',
  reranker_models: '',
  is_active: true,
  priority: 0,
})

const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || '—')

function formatUsd(value: number): string {
  return `$${Number(value || 0).toFixed(2)}`
}

function formatTokens(value: number): string {
  return Number(value || 0).toLocaleString()
}

function splitModels(value: string): string[] {
  return [...new Set(value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean))]
}

function newProvider() {
  Object.assign(providerForm, {
    id: '',
    name: '',
    provider: 'openai_compatible',
    api_key: '',
    base_url: '',
    models: '',
    embedding_models: '',
    reranker_models: '',
    is_active: true,
    priority: 0,
  })
  providerFormOpen.value = true
}

function editProvider(provider: UserProvider) {
  Object.assign(providerForm, {
    id: provider.id,
    name: provider.name,
    provider: provider.provider,
    api_key: '',
    base_url: provider.base_url || '',
    models: (provider.models || []).join('\n'),
    embedding_models: (provider.embedding_models || []).join('\n'),
    reranker_models: (provider.reranker_models || []).join('\n'),
    is_active: provider.is_active,
    priority: provider.priority,
  })
  providerFormOpen.value = true
}

async function saveProvider() {
  if (!providerForm.name.trim() || (!providerForm.id && !providerForm.api_key)) {
    toast.error('名称和 API Key 不能为空')
    return
  }
  providerSaving.value = true
  try {
    const payload: UserProviderPayload = {
      name: providerForm.name.trim(),
      provider: providerForm.provider,
      api_key: providerForm.api_key || undefined,
      base_url: providerForm.base_url.trim() || null,
      models: splitModels(providerForm.models),
      embedding_models: splitModels(providerForm.embedding_models),
      reranker_models: splitModels(providerForm.reranker_models),
      is_active: providerForm.is_active,
      priority: providerForm.priority,
    }
    if (providerForm.id) {
      await updateMyProvider(providerForm.id, payload)
    } else {
      await createMyProvider({ ...payload, api_key: providerForm.api_key })
    }
    providers.value = await getMyProviders()
    providerFormOpen.value = false
    toast.success('自定义 API 已保存')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || '保存自定义 API 失败')
  } finally {
    providerSaving.value = false
  }
}

async function removeProvider(provider: UserProvider) {
  if (!window.confirm(`确认删除自定义 API「${provider.name}」？`)) return
  try {
    await deleteMyProvider(provider.id)
    providers.value = providers.value.filter((item) => item.id !== provider.id)
    if (providerForm.id === provider.id) providerFormOpen.value = false
    toast.success('自定义 API 已删除')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || '删除自定义 API 失败')
  }
}

async function removeSelectedProvider() {
  const provider = providers.value.find((item) => item.id === providerForm.id)
  if (provider) await removeProvider(provider)
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
    const [balanceData, usageData, accountProviders] = await Promise.all([
      getBalance(),
      getUserUsage(userId),
      getMyProviders(),
    ])
    balance.value = balanceData.balance || 0
    dailyUsage.value = balanceData.daily_usage || 0
    monthlyUsage.value = balanceData.monthly_usage || 0
    totalTokens.value = usageData.total_tokens || 0
    totalCost.value = usageData.total_cost || 0
    totalRequests.value = usageData.total_requests || 0
    providers.value = accountProviders
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
            <div class="mb-4 flex items-start justify-between gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <Server class="h-4 w-4 muse-text-muted" />
                  <h2 class="text-base font-semibold muse-text-heading">我的 API</h2>
                </div>
                <p class="mt-1 text-sm muse-text-muted">添加 OpenAI 或 Anthropic 兼容 API。密钥加密保存，保存后不会回显。</p>
              </div>
              <Button variant="secondary" size="sm" @click="newProvider">
                <Plus class="h-4 w-4" />添加 API
              </Button>
            </div>

            <div v-if="providers.length" class="grid gap-3 md:grid-cols-2">
              <button
                v-for="provider in providers"
                :key="provider.id"
                type="button"
                class="rounded-lg border border-[color:var(--muse-border)] p-3 text-left"
                @click="editProvider(provider)"
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="font-medium muse-text-heading">{{ provider.name }}</span>
                  <span class="text-xs" :class="provider.is_active ? 'text-emerald-500' : 'muse-text-faint'">
                    {{ provider.is_active ? '启用' : '停用' }}
                  </span>
                </span>
                <span class="mt-1 block truncate text-xs muse-text-faint">{{ provider.base_url || provider.provider }}</span>
                <span class="mt-2 block text-xs muse-text-muted">
                  LLM {{ provider.models?.length || 0 }} · Embedding {{ provider.embedding_models?.length || 0 }} · Reranker {{ provider.reranker_models?.length || 0 }}
                </span>
              </button>
            </div>
            <p v-else class="rounded-lg bg-[color:var(--muse-surface-muted)] p-3 text-sm muse-text-muted">尚未添加账号自定义 API。</p>

            <div v-if="providerFormOpen" class="mt-4 space-y-4 border-t border-[color:var(--muse-border)] pt-4">
              <div class="grid gap-3 sm:grid-cols-2">
                <label class="text-xs muse-text-muted">名称
                  <Input v-model="providerForm.name" class="mt-1" placeholder="例如：我的 DeepSeek" />
                </label>
                <label class="text-xs muse-text-muted">兼容协议
                  <select v-model="providerForm.provider" class="muse-input mt-1 w-full">
                    <option value="openai_compatible">OpenAI Compatible</option>
                    <option value="anthropic_compatible">Anthropic Compatible</option>
                  </select>
                </label>
                <label class="text-xs muse-text-muted sm:col-span-2">API 地址
                  <Input v-model="providerForm.base_url" class="mt-1" placeholder="https://example.com/v1" />
                </label>
                <label class="text-xs muse-text-muted sm:col-span-2">API Key
                  <Input
                    v-model="providerForm.api_key"
                    type="password"
                    class="mt-1"
                    :placeholder="providerForm.id ? '留空则保持当前密钥' : '输入 API Key'"
                    autocomplete="new-password"
                  />
                </label>
              </div>
              <div class="grid gap-3 lg:grid-cols-3">
                <label class="text-xs muse-text-muted">LLM 模型（每行一个）
                  <textarea v-model="providerForm.models" class="muse-input mt-1 min-h-28 w-full" placeholder="deepseek-v4-flash" />
                </label>
                <label class="text-xs muse-text-muted">Embedding 模型
                  <textarea v-model="providerForm.embedding_models" class="muse-input mt-1 min-h-28 w-full" placeholder="Qwen3-Embedding-0.6B" />
                </label>
                <label class="text-xs muse-text-muted">Reranker 模型
                  <textarea v-model="providerForm.reranker_models" class="muse-input mt-1 min-h-28 w-full" placeholder="Qwen3-Reranker-0.6B" />
                </label>
              </div>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <label class="flex items-center gap-2 text-sm">
                  <input v-model="providerForm.is_active" type="checkbox" />启用此 API
                </label>
                <div class="flex gap-2">
                  <Button
                    v-if="providerForm.id"
                    variant="danger"
                    size="sm"
                    @click="removeSelectedProvider"
                  >
                    <Trash2 class="h-4 w-4" />删除
                  </Button>
                  <Button variant="secondary" size="sm" @click="providerFormOpen = false"><X class="h-4 w-4" />取消</Button>
                  <Button size="sm" :loading="providerSaving" @click="saveProvider"><Save class="h-4 w-4" />保存</Button>
                </div>
              </div>
            </div>
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
