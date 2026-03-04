<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import {
  BarChart3,
  BrainCircuit,
  CreditCard,
  PlugZap,
  SlidersHorizontal,
  Users,
} from 'lucide-vue-next'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Alert from '@/components/ui/Alert.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  getStats, getUsers, createUser, updateUser, deleteUser, addUserBalance,
  getProviders, createProvider, updateProvider, deleteProvider,
  discoverProviderModels, discoverProviderEmbeddingModels, addProviderModel, removeProviderModel,
  addProviderEmbeddingModel, removeProviderEmbeddingModel,
  getPricing, createPricing, updatePricing, deletePricing,
  getPaymentConfig, updatePaymentConfig,
  getOasisConfig, updateOasisConfig,
  getUserOrders,
} from '@/api/admin'
import type {
  AdminUser,
  OasisConfig,
  PaymentConfig,
  PaymentOrderListResponse,
  PricingRule,
  Provider,
  StatsResponse,
  UserListResponse,
} from '@/types'

type Tab = 'overview' | 'users' | 'providers' | 'models' | 'advanced' | 'payments'
type UserStatus = '' | 'ACTIVE' | 'SUSPENDED' | 'DELETED'
type UserAdminFilter = '' | 'true' | 'false'

const tab = ref<Tab>('overview')
const loading = ref(true)
const stats = ref<StatsResponse | null>(null)
const usersData = ref<UserListResponse | null>(null)
const providers = ref<Provider[]>([])
const pricingRules = ref<PricingRule[]>([])
const paymentConfig = ref<PaymentConfig>({
  enabled: false,
  url: '',
  pid: '',
  key: '',
  has_key: false,
  payment_type: 'alipay',
  notify_url: '',
  return_url: '',
})
const paymentKeyInput = ref('')
const page = ref(1)
const pageSize = 20
const userFilters = ref<{ search: string; is_admin: UserAdminFilter; status: UserStatus }>({
  search: '',
  is_admin: '',
  status: '',
})
const rowBalanceInput = ref<Record<string, string>>({})

const userForm = ref({ email: '', password: '', nickname: '', is_admin: false, balance: 0 })
const showUserForm = ref(false)

const providerForm = ref<{ id: string; name: string; provider: string; api_key: string; base_url: string; is_active: boolean; priority: number }>({
  id: '',
  name: '',
  provider: 'openai_compatible',
  api_key: '',
  base_url: '',
  is_active: true,
  priority: 0,
})
const showProviderForm = ref(false)
const providerTypeOptions = (import.meta.env.VITE_PROVIDER_TYPES || 'openai_compatible,anthropic_compatible')
  .split(',')
  .map((item: string) => item.trim())
  .filter((item: string) => item.length > 0)

const providerModelProviderId = ref('')
const providerModelFormKind = ref<'chat' | 'embedding'>('chat')
const providerModelManualInput = ref('')
const discoveredProviderModels = ref<string[]>([])
const discoveredProviderModel = ref('')
const providerModelMessage = ref('')
const providerModelError = ref('')
const discoveredProviderEmbeddingModels = ref<string[]>([])
const discoveredProviderEmbeddingModel = ref('')
const providerEmbeddingMessage = ref('')
const providerEmbeddingError = ref('')
const showModelForm = ref(false)

const oasisConfig = ref<OasisConfig>({
  analysis_prompt_prefix: '',
  simulation_prompt_prefix: '',
  report_prompt_prefix: '',
  max_agent_profiles: 16,
  max_events: 16,
  max_agent_activity: 48,
  min_total_hours: 6,
  max_total_hours: 336,
  min_minutes_per_round: 10,
  max_minutes_per_round: 240,
  max_posts_per_hour: 20,
  max_response_delay_minutes: 720,
  allowed_platforms: [],
  llm_request_timeout_seconds: 120,
  llm_retry_count: 2,
  llm_retry_interval_seconds: 1.5,
})
const llmRequestConfigMessage = ref('')
const llmRequestConfigError = ref('')
const oasisAdvancedConfigMessage = ref('')
const oasisAdvancedConfigError = ref('')

const expandedUserOrdersId = ref<string | null>(null)
const userOrdersLoading = ref(false)
const userOrdersError = ref('')
const userOrdersData = ref<PaymentOrderListResponse | null>(null)

const FIXED_TOKEN_UNIT = 1_000_000
const showPricingForm = ref(false)
const pricingForm = ref<{
  id: string
  model: string
  billing_mode: 'TOKEN' | 'REQUEST'
  input_price: number
  output_price: number
  request_price: number
  is_active: boolean
}>({
  id: '',
  model: '',
  billing_mode: 'TOKEN',
  input_price: 0,
  output_price: 0,
  request_price: 0,
  is_active: true,
})
const pricingFormError = ref('')


const tabItems: Array<{ value: Tab; label: string; icon: Component; hint: string }> = [
  { value: 'overview', label: 'Overview', icon: BarChart3, hint: '系统统计' },
  { value: 'users', label: 'Users', icon: Users, hint: '用户管理' },
  { value: 'providers', label: 'Providers', icon: PlugZap, hint: '渠道配置' },
  { value: 'models', label: 'Models', icon: BrainCircuit, hint: '模型与计费' },
  { value: 'advanced', label: 'Advanced', icon: SlidersHorizontal, hint: '高级设置' },
  { value: 'payments', label: 'Payments', icon: CreditCard, hint: '支付配置' },
]

const discoveredModelsForCurrentKind = computed(() =>
  providerModelFormKind.value === 'embedding'
    ? discoveredProviderEmbeddingModels.value
    : discoveredProviderModels.value
)
const discoveredModelForCurrentKind = computed({
  get: () =>
    providerModelFormKind.value === 'embedding'
      ? discoveredProviderEmbeddingModel.value
      : discoveredProviderModel.value,
  set: (value: string) => {
    if (providerModelFormKind.value === 'embedding') {
      discoveredProviderEmbeddingModel.value = value
      return
    }
    discoveredProviderModel.value = value
  },
})
const providerModelMessageForCurrentKind = computed(() =>
  providerModelFormKind.value === 'embedding'
    ? providerEmbeddingMessage.value
    : providerModelMessage.value
)
const providerModelErrorForCurrentKind = computed(() =>
  providerModelFormKind.value === 'embedding'
    ? providerEmbeddingError.value
    : providerModelError.value
)
const knownModels = computed(() =>
  Array.from(
    new Set([
      ...providers.value.flatMap((p) => p.models || []),
      ...providers.value.flatMap((p) => p.embedding_models || []),
      ...pricingRules.value.map((r) => r.model),
    ])
  ).sort()
)
const totalKnownModels = computed(() => knownModels.value.length)
const oasisAllowedPlatformsInput = computed({
  get: () => oasisConfig.value.allowed_platforms.join(', '),
  set: (value: string) => {
    oasisConfig.value.allowed_platforms = value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
  },
})

function pricingByModel(model: string): PricingRule | undefined {
  return pricingRules.value.find((r) => r.model === model)
}

function providerNameForModel(model: string): string {
  const names = providers.value
    .filter((p) => (p.models || []).includes(model) || (p.embedding_models || []).includes(model))
    .map((p) => p.name)
  return names.length ? names.join(', ') : '—'
}

function modelTypeForModel(model: string): string {
  const inLlm = providers.value.some((p) => (p.models || []).includes(model))
  const inEmbedding = providers.value.some((p) => (p.embedding_models || []).includes(model))
  if (inLlm && inEmbedding) return 'LLM + Embedding'
  if (inEmbedding) return 'Embedding'
  if (inLlm) return 'LLM'
  return '—'
}

function formatPricing(rule?: PricingRule): string {
  if (!rule) return '未配置'
  if (rule.billing_mode === 'REQUEST') return '$' + rule.request_price.toFixed(6) + ' / request'
  return '$' + rule.input_price.toFixed(6) + ' in + $' + rule.output_price.toFixed(6) + ' out / 1M tokens'
}

function statusChipClass(value: string) {
  const status = (value || '').toUpperCase()
  if (status === 'ACTIVE') {
    return 'border-emerald-300/70 bg-emerald-100 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  if (status === 'SUSPENDED') {
    return 'border-amber-300/80 bg-amber-100 text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (status === 'DELETED') {
    return 'border-red-300/80 bg-red-100 text-red-700 dark:border-red-700/50 dark:bg-red-900/20 dark:text-red-300'
  }
  return 'border-stone-300 bg-stone-100 text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function orderStatusChipClass(value: string) {
  const status = (value || '').toUpperCase()
  if (status === 'PAID' || status === 'SUCCESS') {
    return 'border-emerald-300/70 bg-emerald-100 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  if (status === 'PENDING' || status === 'UNPAID') {
    return 'border-amber-300/80 bg-amber-100 text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (status === 'FAILED' || status === 'CANCELLED' || status === 'CLOSED') {
    return 'border-red-300/80 bg-red-100 text-red-700 dark:border-red-700/50 dark:bg-red-900/20 dark:text-red-300'
  }
  return 'border-stone-300 bg-stone-100 text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function getUserTokenUsage(user: AdminUser) {
  return {
    totalTokens: Number(
      user.usage?.total_tokens
      ?? user.token_usage?.total_tokens
      ?? user.total_tokens
      ?? 0,
    ),
    requestCount: Number(
      user.usage?.total_requests
      ?? user.token_usage?.request_count
      ?? user.total_requests
      ?? 0,
    ),
    totalCost: Number(
      user.usage?.total_cost
      ?? user.token_usage?.total_cost
      ?? user.total_cost
      ?? 0,
    ),
  }
}

function getUserRechargeSummary(user: AdminUser) {
  return {
    totalOrders: Number(
      user.recharge?.total_orders
      ?? user.recharge_summary?.total_orders
      ?? user.total_orders
      ?? 0,
    ),
    paidOrders: Number(
      user.recharge?.paid_orders
      ?? user.recharge_summary?.paid_orders
      ?? user.paid_orders
      ?? 0,
    ),
    paidAmount: Number(
      user.recharge?.paid_amount
      ?? user.recharge_summary?.paid_amount
      ?? user.paid_amount
      ?? 0,
    ),
  }
}

function formatCurrency(value?: number, digits = 6): string {
  return Number(value || 0).toFixed(digits)
}

function formatTokens(value?: number): string {
  return Number(value || 0).toLocaleString()
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null) {
    const maybeResponse = error as {
      response?: { data?: { detail?: string; message?: string } }
      message?: string
    }
    return maybeResponse.response?.data?.detail
      || maybeResponse.response?.data?.message
      || maybeResponse.message
      || fallback
  }
  return fallback
}

function buildUserFilters() {
  const search = userFilters.value.search.trim()
  return {
    ...(search ? { search } : {}),
    ...(userFilters.value.is_admin !== '' ? { is_admin: userFilters.value.is_admin === 'true' } : {}),
    ...(userFilters.value.status ? { status: userFilters.value.status } : {}),
  }
}

async function loadUsers() {
  usersData.value = await getUsers(page.value, pageSize, buildUserFilters())
}

async function loadAll() {
  loading.value = true
  await Promise.all([
    getStats().then((d) => (stats.value = d)).catch(() => {}),
    loadUsers().catch(() => {}),
    getProviders().then((d) => (providers.value = d)).catch(() => {}),
    getPricing().then((d) => (pricingRules.value = d)).catch(() => {}),
    getPaymentConfig().then((d) => (paymentConfig.value = d)).catch(() => {}),
    getOasisConfig().then((d) => (oasisConfig.value = d)).catch(() => {}),
  ])
  if (!providerModelProviderId.value && providers.value.length) {
    providerModelProviderId.value = providers.value[0].id
  }
  loading.value = false
}

async function refreshProviders() {
  providers.value = await getProviders()
  if (!providerModelProviderId.value && providers.value.length) {
    providerModelProviderId.value = providers.value[0].id
  }
  if (providerModelProviderId.value && !providers.value.some((p) => p.id === providerModelProviderId.value)) {
    providerModelProviderId.value = providers.value[0]?.id || ''
  }
}

async function saveUser() {
  await createUser({
    email: userForm.value.email,
    password: userForm.value.password,
    nickname: userForm.value.nickname,
    is_admin: userForm.value.is_admin,
    balance: Number(userForm.value.balance || 0),
  })
  showUserForm.value = false
  userForm.value = { email: '', password: '', nickname: '', is_admin: false, balance: 0 }
  await loadUsers()
}

async function removeUser(id: string) {
  await deleteUser(id)
  await loadUsers()
}

async function toggleAdmin(id: string, v: boolean) {
  await updateUser(id, { is_admin: v })
  await loadUsers()
}

async function addBalanceForUser(id: string) {
  const amount = Number(rowBalanceInput.value[id] || 0)
  if (!amount) return
  await addUserBalance(id, amount)
  rowBalanceInput.value[id] = ''
  await loadUsers()
}

async function applyUserFilters() {
  page.value = 1
  await loadUsers()
}

async function resetUserFilters() {
  userFilters.value = { search: '', is_admin: '', status: '' }
  page.value = 1
  await loadUsers()
}

function editProvider(p: Provider) {
  providerForm.value = { id: p.id, name: p.name, provider: p.provider, api_key: '', base_url: p.base_url || '', is_active: p.is_active, priority: p.priority }
  showProviderForm.value = true
}

function newProvider() {
  providerForm.value = { id: '', name: '', provider: 'openai_compatible', api_key: '', base_url: '', is_active: true, priority: 0 }
  showProviderForm.value = true
}

async function saveProvider() {
  const providerType = providerForm.value.provider.trim()
  if (!providerType) return
  const payload: {
    name: string
    provider: string
    api_key?: string
    base_url: string | null
    is_active: boolean
    priority: number
  } = {
    name: providerForm.value.name,
    provider: providerType,
    api_key: providerForm.value.api_key,
    base_url: providerForm.value.base_url || null,
    is_active: providerForm.value.is_active,
    priority: providerForm.value.priority,
  }
  if (providerForm.value.id) {
    if (!payload.api_key) delete payload.api_key
    await updateProvider(providerForm.value.id, payload)
  } else {
    await createProvider({
      name: payload.name,
      provider: payload.provider,
      api_key: payload.api_key || '',
      base_url: payload.base_url,
      is_active: payload.is_active,
      priority: payload.priority,
    })
  }
  showProviderForm.value = false
  await refreshProviders()
}

async function removeProvider(id: string) {
  await deleteProvider(id)
  await refreshProviders()
}

type ProviderModelKind = 'chat' | 'embedding'
type ProviderModelAction = 'add' | 'remove'

function clearProviderModelFeedback(kind: ProviderModelKind) {
  if (kind === 'embedding') {
    providerEmbeddingError.value = ''
    providerEmbeddingMessage.value = ''
    return
  }
  providerModelError.value = ''
  providerModelMessage.value = ''
}

function setProviderModelMessage(kind: ProviderModelKind, message: string) {
  if (kind === 'embedding') {
    providerEmbeddingMessage.value = message
    return
  }
  providerModelMessage.value = message
}

function setProviderModelError(kind: ProviderModelKind, message: string) {
  if (kind === 'embedding') {
    providerEmbeddingError.value = message
    return
  }
  providerModelError.value = message
}

async function refreshDiscover(kind: ProviderModelKind, persist = false) {
  if (!providerModelProviderId.value) return
  clearProviderModelFeedback(kind)
  try {
    if (kind === 'embedding') {
      const discovered = await discoverProviderEmbeddingModels(providerModelProviderId.value, persist)
      discoveredProviderEmbeddingModels.value = discovered.discovered
      discoveredProviderEmbeddingModel.value = discovered.discovered[0] || ''
      if (persist) await refreshProviders()
      setProviderModelMessage(kind, `${persist ? 'Imported' : 'Discovered'} ${discovered.discovered.length}`)
      return
    }

    const discovered = await discoverProviderModels(providerModelProviderId.value, persist)
    discoveredProviderModels.value = discovered.discovered
    discoveredProviderModel.value = discovered.discovered[0] || ''
    if (persist) await refreshProviders()
    setProviderModelMessage(kind, `${persist ? 'Imported' : 'Discovered'} ${discovered.discovered.length}`)
  } catch (error: unknown) {
    setProviderModelError(kind, getErrorMessage(error, 'Discover failed'))
  }
}

async function mutateProviderModel(kind: ProviderModelKind, action: ProviderModelAction, model: string) {
  if (!providerModelProviderId.value) return
  const modelId = model.trim()
  if (!modelId) return
  clearProviderModelFeedback(kind)
  try {
    let next: string[] = []
    if (kind === 'embedding') {
      next = action === 'add'
        ? await addProviderEmbeddingModel(providerModelProviderId.value, modelId)
        : await removeProviderEmbeddingModel(providerModelProviderId.value, modelId)
      setProviderModelMessage(kind, `Embedding models: ${next.length}`)
    } else {
      next = action === 'add'
        ? await addProviderModel(providerModelProviderId.value, modelId)
        : await removeProviderModel(providerModelProviderId.value, modelId)
      setProviderModelMessage(kind, `LLM models: ${next.length}`)
    }
    await refreshProviders()
  } catch (error: unknown) {
    const actionLabel = action === 'add' ? 'Add' : 'Remove'
    const kindLabel = kind === 'embedding' ? 'embedding model' : 'model'
    setProviderModelError(kind, getErrorMessage(error, `${actionLabel} ${kindLabel} failed`))
  }
}

async function addModelManualByKind() {
  if (!providerModelProviderId.value || !providerModelManualInput.value.trim()) return
  await mutateProviderModel(providerModelFormKind.value, 'add', providerModelManualInput.value)
  providerModelManualInput.value = ''
}

async function addModelDiscoveredByKind() {
  if (!providerModelProviderId.value || !discoveredModelForCurrentKind.value) return
  await mutateProviderModel(providerModelFormKind.value, 'add', discoveredModelForCurrentKind.value)
}

function resetModelDiscoverState() {
  discoveredProviderModel.value = ''
  discoveredProviderModels.value = []
  discoveredProviderEmbeddingModel.value = ''
  discoveredProviderEmbeddingModels.value = []
}

function openModelForm() {
  providerModelFormKind.value = 'chat'
  resetModelDiscoverState()
  providerModelError.value = ''
  providerModelMessage.value = ''
  providerEmbeddingError.value = ''
  providerEmbeddingMessage.value = ''
  showModelForm.value = true
}

function closeModelForm() {
  showModelForm.value = false
  providerModelManualInput.value = ''
  resetModelDiscoverState()
  providerModelError.value = ''
  providerModelMessage.value = ''
  providerEmbeddingError.value = ''
  providerEmbeddingMessage.value = ''
}

watch(providerModelProviderId, () => {
  resetModelDiscoverState()
  providerModelManualInput.value = ''
  clearProviderModelFeedback('chat')
  clearProviderModelFeedback('embedding')
})

watch(providerModelFormKind, () => {
  providerModelManualInput.value = ''
  clearProviderModelFeedback('chat')
  clearProviderModelFeedback('embedding')
})

function applyLlmRequestFields(next: OasisConfig) {
  oasisConfig.value.llm_request_timeout_seconds = next.llm_request_timeout_seconds
  oasisConfig.value.llm_retry_count = next.llm_retry_count
  oasisConfig.value.llm_retry_interval_seconds = next.llm_retry_interval_seconds
}

function applyOasisAdvancedFields(next: OasisConfig) {
  oasisConfig.value.analysis_prompt_prefix = next.analysis_prompt_prefix
  oasisConfig.value.simulation_prompt_prefix = next.simulation_prompt_prefix
  oasisConfig.value.report_prompt_prefix = next.report_prompt_prefix
  oasisConfig.value.max_agent_profiles = next.max_agent_profiles
  oasisConfig.value.max_events = next.max_events
  oasisConfig.value.max_agent_activity = next.max_agent_activity
  oasisConfig.value.min_total_hours = next.min_total_hours
  oasisConfig.value.max_total_hours = next.max_total_hours
  oasisConfig.value.min_minutes_per_round = next.min_minutes_per_round
  oasisConfig.value.max_minutes_per_round = next.max_minutes_per_round
  oasisConfig.value.max_posts_per_hour = next.max_posts_per_hour
  oasisConfig.value.max_response_delay_minutes = next.max_response_delay_minutes
  oasisConfig.value.allowed_platforms = [...next.allowed_platforms]
}

async function saveLlmRequestConfig() {
  llmRequestConfigError.value = ''
  llmRequestConfigMessage.value = ''
  try {
    const updated = await updateOasisConfig({
      llm_request_timeout_seconds: Number(oasisConfig.value.llm_request_timeout_seconds || 0),
      llm_retry_count: Number(oasisConfig.value.llm_retry_count || 0),
      llm_retry_interval_seconds: Number(oasisConfig.value.llm_retry_interval_seconds || 0),
    })
    applyLlmRequestFields(updated)
    llmRequestConfigMessage.value = 'LLM request config updated'
  } catch (error: unknown) {
    llmRequestConfigError.value = getErrorMessage(error, 'Save LLM request config failed')
  }
}

async function reloadLlmRequestConfig() {
  llmRequestConfigError.value = ''
  llmRequestConfigMessage.value = ''
  try {
    const latest = await getOasisConfig()
    applyLlmRequestFields(latest)
    llmRequestConfigMessage.value = 'LLM request config refreshed'
  } catch (error: unknown) {
    llmRequestConfigError.value = getErrorMessage(error, 'Load LLM request config failed')
  }
}

async function saveOasisAdvancedConfig() {
  oasisAdvancedConfigError.value = ''
  oasisAdvancedConfigMessage.value = ''
  try {
    const updated = await updateOasisConfig({
      analysis_prompt_prefix: oasisConfig.value.analysis_prompt_prefix,
      simulation_prompt_prefix: oasisConfig.value.simulation_prompt_prefix,
      report_prompt_prefix: oasisConfig.value.report_prompt_prefix,
      max_agent_profiles: Number(oasisConfig.value.max_agent_profiles || 0),
      max_events: Number(oasisConfig.value.max_events || 0),
      max_agent_activity: Number(oasisConfig.value.max_agent_activity || 0),
      min_total_hours: Number(oasisConfig.value.min_total_hours || 0),
      max_total_hours: Number(oasisConfig.value.max_total_hours || 0),
      min_minutes_per_round: Number(oasisConfig.value.min_minutes_per_round || 0),
      max_minutes_per_round: Number(oasisConfig.value.max_minutes_per_round || 0),
      max_posts_per_hour: Number(oasisConfig.value.max_posts_per_hour || 0),
      max_response_delay_minutes: Number(oasisConfig.value.max_response_delay_minutes || 0),
      allowed_platforms: oasisConfig.value.allowed_platforms,
    })
    applyOasisAdvancedFields(updated)
    oasisAdvancedConfigMessage.value = 'OASIS config updated'
  } catch (error: unknown) {
    oasisAdvancedConfigError.value = getErrorMessage(error, 'Save OASIS config failed')
  }
}

async function reloadOasisAdvancedConfig() {
  oasisAdvancedConfigError.value = ''
  oasisAdvancedConfigMessage.value = ''
  try {
    const latest = await getOasisConfig()
    applyOasisAdvancedFields(latest)
    oasisAdvancedConfigMessage.value = 'OASIS config refreshed'
  } catch (error: unknown) {
    oasisAdvancedConfigError.value = getErrorMessage(error, 'Load OASIS config failed')
  }
}

async function toggleUserOrders(user: AdminUser) {
  if (expandedUserOrdersId.value === user.id) {
    expandedUserOrdersId.value = null
    userOrdersData.value = null
    userOrdersError.value = ''
    return
  }
  expandedUserOrdersId.value = user.id
  await loadUserOrders(user.id)
}

async function loadUserOrders(userId: string) {
  userOrdersLoading.value = true
  userOrdersError.value = ''
  try {
    userOrdersData.value = await getUserOrders(userId, 1, 20)
  } catch (error: unknown) {
    userOrdersError.value = getErrorMessage(error, 'Load user orders failed')
    userOrdersData.value = null
  } finally {
    userOrdersLoading.value = false
  }
}

async function removeModel(model: string) {
  const relatedLlmProviders = providers.value.filter((p) => (p.models || []).includes(model))
  const relatedEmbeddingProviders = providers.value.filter((p) => (p.embedding_models || []).includes(model))
  const relatedRule = pricingByModel(model)
  if (!relatedLlmProviders.length && !relatedEmbeddingProviders.length && !relatedRule) return

  const confirmed = window.confirm(
    `Delete model "${model}" from providers${relatedRule ? ' and pricing rules' : ''}?`
  )
  if (!confirmed) return

  for (const provider of relatedLlmProviders) {
    await removeProviderModel(provider.id, model)
  }
  for (const provider of relatedEmbeddingProviders) {
    await removeProviderEmbeddingModel(provider.id, model)
  }
  if (relatedRule) {
    await deletePricing(relatedRule.id)
  }

  await refreshProviders()
  pricingRules.value = await getPricing()
}

function newPricing(model = '') {
  pricingFormError.value = ''
  pricingForm.value = {
    id: '',
    model,
    billing_mode: 'TOKEN',
    input_price: 0,
    output_price: 0,
    request_price: 0,
    is_active: true,
  }
  showPricingForm.value = true
}

function editPricing(rule: PricingRule) {
  pricingFormError.value = ''
  pricingForm.value = {
    id: rule.id,
    model: rule.model,
    billing_mode: rule.billing_mode,
    input_price: Number(rule.input_price || 0),
    output_price: Number(rule.output_price || 0),
    request_price: Number(rule.request_price || 0),
    is_active: !!rule.is_active,
  }
  showPricingForm.value = true
}

async function savePricing() {
  pricingFormError.value = ''
  const model = pricingForm.value.model.trim()
  if (!model) {
    pricingFormError.value = 'Model is required'
    return
  }

  const payload = {
    model,
    billing_mode: pricingForm.value.billing_mode,
    input_price: Number(pricingForm.value.input_price || 0),
    output_price: Number(pricingForm.value.output_price || 0),
    token_unit: FIXED_TOKEN_UNIT,
    request_price: Number(pricingForm.value.request_price || 0),
    is_active: !!pricingForm.value.is_active,
  }
  if (pricingForm.value.id) await updatePricing(pricingForm.value.id, payload)
  else await createPricing(payload)

  pricingRules.value = await getPricing()
  showPricingForm.value = false
}

async function savePayment() {
  const payload = {
    enabled: paymentConfig.value.enabled,
    url: paymentConfig.value.url,
    pid: paymentConfig.value.pid,
    key: paymentKeyInput.value.trim(),
    payment_type: paymentConfig.value.payment_type,
    notify_url: paymentConfig.value.notify_url,
    return_url: paymentConfig.value.return_url,
  }
  paymentConfig.value = await updatePaymentConfig(payload)
  paymentKeyInput.value = ''
}

function nextPage() {
  if (usersData.value && page.value * pageSize < usersData.value.total) {
    page.value++
    loadUsers()
  }
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadUsers()
  }
}

onMounted(loadAll)
</script>

<template>
  <AdminLayout>
    <div class="space-y-6">
      <section class="rounded-xl border border-stone-300/80 bg-stone-50/80 px-4 py-4 shadow-sm dark:border-zinc-700/60 dark:bg-zinc-800/50">
        <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div class="space-y-1">
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Admin Panel</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400">管理用户、渠道、模型计费与支付配置</p>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
            <div class="rounded-lg border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Providers</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ providers.length }}</p>
            </div>
            <div class="rounded-lg border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Models</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ totalKnownModels }}</p>
            </div>
            <div class="rounded-lg border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Pricing Rules</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ pricingRules.length }}</p>
            </div>
          </div>
        </div>
      </section>

      <Tabs v-model="tab" class="space-y-4">
        <TabsList class="grid h-auto w-full grid-cols-2 gap-1 bg-stone-100/80 p-1 md:grid-cols-6 dark:bg-zinc-800/80">
          <TabsTrigger
            v-for="item in tabItems"
            :key="item.value"
            :value="item.value"
            class="h-auto py-2"
          >
            <component :is="item.icon" class="h-3.5 w-3.5" />
            <span>{{ item.label }}</span>
            <span class="hidden text-[10px] text-stone-500 dark:text-zinc-400 md:inline">{{ item.hint }}</span>
          </TabsTrigger>
        </TabsList>

        <Card v-if="loading">
          <p class="text-sm text-stone-600 dark:text-zinc-300">Loading admin data...</p>
        </Card>

        <template v-else>
          <TabsContent value="overview" class="space-y-4">
            <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Users</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_users ?? 0 }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Projects</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_projects ?? 0 }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Operations</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.total_operations ?? 0 }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Revenue</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_revenue, 2) }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Usage Cost</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_usage_cost) }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Total Tokens</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatTokens(stats?.total_tokens) }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">24h Tokens</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatTokens(stats?.last_24h_tokens) }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">Total Balance</p>
                <p class="text-2xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.total_balance) }}</p>
              </Card>
            </div>

            <div class="grid gap-3 md:grid-cols-3">
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">24h Requests</p>
                <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ stats?.last_24h_request_count ?? 0 }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">7d Cost</p>
                <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.last_7d_cost) }}</p>
              </Card>
              <Card class="space-y-1">
                <p class="text-xs uppercase tracking-wide text-stone-500 dark:text-zinc-400">30d Cost</p>
                <p class="text-xl font-semibold text-stone-800 dark:text-zinc-100">{{ formatCurrency(stats?.last_30d_cost) }}</p>
              </Card>
            </div>

            <div class="grid gap-3 md:grid-cols-2">
              <Card :padding="false">
                <div class="border-b border-stone-300/80 px-3 py-3 sm:px-4 dark:border-zinc-700/60">
                  <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Top Users By Cost</p>
                </div>
                <div class="py-3 sm:py-4">
                  <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                    <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                      <tr class="border-b border-stone-300 dark:border-zinc-700">
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">User</th>
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Req</th>
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Tokens</th>
                        <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="u in stats?.top_users ?? []"
                        :key="u.user_id"
                        class="border-b border-stone-200/80 dark:border-zinc-800"
                      >
                        <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">
                          <p class="max-w-[220px] truncate">{{ u.nickname || u.email }}</p>
                          <p class="max-w-[220px] truncate text-xs text-stone-500 dark:text-zinc-400">{{ u.email }}</p>
                        </td>
                        <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ u.request_count }}</td>
                        <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatTokens(u.total_tokens) }}</td>
                        <td class="px-3 py-2 text-right text-stone-700 dark:text-zinc-100">{{ formatCurrency(u.cost) }}</td>
                      </tr>
                      <tr v-if="!(stats?.top_users?.length)">
                        <td colspan="4" class="px-3 py-3 text-center text-xs text-stone-500 dark:text-zinc-400">No usage data</td>
                      </tr>
                    </tbody>
                    </table>
                  </div>
                </div>
              </Card>

              <Card :padding="false">
                <div class="border-b border-stone-300/80 px-3 py-3 sm:px-4 dark:border-zinc-700/60">
                  <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Top Models By Cost</p>
                </div>
                <div class="py-3 sm:py-4">
                  <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                    <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                      <tr class="border-b border-stone-300 dark:border-zinc-700">
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Model</th>
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Req</th>
                        <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Tokens</th>
                        <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="m in stats?.top_models ?? []"
                        :key="m.model"
                        class="border-b border-stone-200/80 dark:border-zinc-800"
                      >
                        <td class="px-3 py-2 font-mono text-xs text-stone-700 dark:text-zinc-200">{{ m.model }}</td>
                        <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ m.request_count }}</td>
                        <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatTokens(m.total_tokens) }}</td>
                        <td class="px-3 py-2 text-right text-stone-700 dark:text-zinc-100">{{ formatCurrency(m.cost) }}</td>
                      </tr>
                      <tr v-if="!(stats?.top_models?.length)">
                        <td colspan="4" class="px-3 py-3 text-center text-xs text-stone-500 dark:text-zinc-400">No model data</td>
                      </tr>
                    </tbody>
                    </table>
                  </div>
                </div>
              </Card>
            </div>

            <Card class="space-y-2">
              <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">Usage Audit</p>
              <div class="grid gap-2 text-xs text-stone-600 md:grid-cols-2 dark:text-zinc-300">
                <div>Missing operation id: {{ stats?.usage_audit?.usage_without_operation ?? 0 }}</div>
                <div>Missing project id: {{ stats?.usage_audit?.usage_without_project ?? 0 }}</div>
                <div>Missing operation record: {{ stats?.usage_audit?.usage_with_missing_operation_record ?? 0 }}</div>
                <div>Missing project record: {{ stats?.usage_audit?.usage_with_missing_project_record ?? 0 }}</div>
                <div>Project user mismatch: {{ stats?.usage_audit?.usage_with_project_user_mismatch ?? 0 }}</div>
                <div>Operation user mismatch: {{ stats?.usage_audit?.usage_with_operation_user_mismatch ?? 0 }}</div>
                <div>Operation value mismatch: {{ stats?.usage_audit?.usage_operation_value_mismatch ?? 0 }}</div>
                <div>Negative balance users: {{ stats?.usage_audit?.negative_balance_users ?? 0 }}</div>
              </div>
            </Card>
        </TabsContent>

          <TabsContent value="users" class="space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
              <div class="space-y-0.5">
                <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Users</h2>
                <p class="text-xs text-stone-500 dark:text-zinc-400">当前总数 {{ usersData?.total ?? 0 }}</p>
              </div>
              <Button size="sm" @click="showUserForm = true">New User</Button>
            </div>

            <Card class="space-y-3">
              <div class="grid gap-2 md:grid-cols-3">
                <Input
                  v-model="userFilters.search"
                  placeholder="Search email / nickname"
                  @keyup.enter="applyUserFilters"
                />
                <Select v-model="userFilters.is_admin">
                  <option value="">All Roles</option>
                  <option value="true">Admin</option>
                  <option value="false">User</option>
                </Select>
                <Select v-model="userFilters.status">
                  <option value="">All Status</option>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="SUSPENDED">SUSPENDED</option>
                  <option value="DELETED">DELETED</option>
                </Select>
              </div>
              <div class="flex justify-end gap-2">
                <Button size="sm" variant="secondary" @click="resetUserFilters">Reset</Button>
                <Button size="sm" @click="applyUserFilters">Search</Button>
              </div>
            </Card>

            <Card v-if="showUserForm" class="space-y-3">
              <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Create User</h3>
              <div class="grid gap-2 md:grid-cols-2">
                <Input v-model="userForm.email" placeholder="Email" />
                <Input v-model="userForm.nickname" placeholder="Nickname" />
                <Input v-model="userForm.password" type="password" placeholder="Password" />
                <Input v-model.number="userForm.balance" type="number" min="0" step="0.01" placeholder="Initial Balance" />
                <Select v-model="userForm.is_admin">
                  <option :value="false">Normal User</option>
                  <option :value="true">Administrator</option>
                </Select>
              </div>
              <div class="flex justify-end gap-2">
                <Button size="sm" variant="secondary" @click="showUserForm = false">Cancel</Button>
                <Button size="sm" @click="saveUser">Save</Button>
              </div>
            </Card>

            <Card :padding="false">
              <div class="py-3 sm:py-4">
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                  <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                    <tr class="border-b border-stone-300 dark:border-zinc-700">
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Nickname</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Email</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Admin</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Status</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Balance</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Token Usage</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Recharge</th>
                      <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="u in usersData?.users ?? []" :key="u.id">
                      <tr
                        class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                      >
                        <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ u.nickname || '—' }}</td>
                        <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ u.email }}</td>
                        <td class="px-3 py-2">
                          <Button size="sm" variant="secondary" @click="toggleAdmin(u.id, !u.is_admin)">
                            {{ u.is_admin ? 'Remove Admin' : 'Make Admin' }}
                          </Button>
                        </td>
                        <td class="px-3 py-2">
                          <span :class="['inline-flex rounded-full border px-2 py-0.5 text-xs font-medium', statusChipClass(u.status)]">
                            {{ u.status }}
                          </span>
                        </td>
                        <td class="px-3 py-2">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="text-stone-700 dark:text-zinc-200">{{ Number(u.balance).toFixed(2) }}</span>
                            <Input
                              v-model="rowBalanceInput[u.id]"
                              type="number"
                              step="0.01"
                              class="w-28"
                              placeholder="+金额"
                            />
                            <Button size="sm" variant="secondary" @click="addBalanceForUser(u.id)">加余额</Button>
                          </div>
                        </td>
                        <td class="px-3 py-2">
                          <div class="space-y-0.5 text-xs">
                            <p class="text-stone-700 dark:text-zinc-200">{{ formatTokens(getUserTokenUsage(u).totalTokens) }} tokens</p>
                            <p class="text-stone-500 dark:text-zinc-400">{{ getUserTokenUsage(u).requestCount }} req · ${{ formatCurrency(getUserTokenUsage(u).totalCost) }}</p>
                          </div>
                        </td>
                        <td class="px-3 py-2">
                          <div class="space-y-0.5 text-xs">
                            <p class="text-stone-700 dark:text-zinc-200">{{ getUserRechargeSummary(u).totalOrders }} orders</p>
                            <p class="text-stone-500 dark:text-zinc-400">paid {{ getUserRechargeSummary(u).paidOrders }} · ${{ formatCurrency(getUserRechargeSummary(u).paidAmount, 2) }}</p>
                          </div>
                        </td>
                        <td class="px-3 py-2 text-right">
                          <div class="flex flex-wrap justify-end gap-2">
                            <Button size="sm" variant="secondary" @click="toggleUserOrders(u)">
                              {{ expandedUserOrdersId === u.id ? 'Hide Orders' : 'View Orders' }}
                            </Button>
                            <Button size="sm" variant="danger" @click="removeUser(u.id)">Delete</Button>
                          </div>
                        </td>
                      </tr>
                      <tr v-if="expandedUserOrdersId === u.id" class="border-b border-stone-200/80 bg-stone-100/40 dark:border-zinc-800 dark:bg-zinc-900/20">
                        <td colspan="8" class="px-3 py-3">
                          <div class="space-y-3">
                            <div class="flex items-center justify-between gap-2">
                              <p class="text-sm font-medium text-stone-700 dark:text-zinc-200">充值订单 · {{ u.nickname || u.email }}</p>
                              <Button size="sm" variant="secondary" @click="loadUserOrders(u.id)">Refresh</Button>
                            </div>

                            <Alert v-if="userOrdersError" variant="destructive">{{ userOrdersError }}</Alert>

                            <div v-if="userOrdersLoading" class="text-xs text-stone-500 dark:text-zinc-400">
                              Loading orders...
                            </div>

                            <div v-else-if="userOrdersData?.orders?.length" class="overflow-x-auto">
                              <table class="w-full text-xs">
                                <thead class="bg-stone-200/60 dark:bg-zinc-800/70">
                                  <tr class="border-b border-stone-300 dark:border-zinc-700">
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Order No</th>
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Amount</th>
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Status</th>
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Method</th>
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Created</th>
                                    <th class="px-2 py-1.5 text-left font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Paid</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr
                                    v-for="order in userOrdersData.orders"
                                    :key="order.id || order.order_no"
                                    class="border-b border-stone-200/80 dark:border-zinc-800"
                                  >
                                    <td class="px-2 py-1.5 font-mono text-stone-700 dark:text-zinc-200">{{ order.order_no }}</td>
                                    <td class="px-2 py-1.5 text-stone-700 dark:text-zinc-200">${{ formatCurrency(order.amount, 2) }}</td>
                                    <td class="px-2 py-1.5">
                                      <span :class="['inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium', orderStatusChipClass(order.status)]">
                                        {{ order.status }}
                                      </span>
                                    </td>
                                    <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ order.payment_method || '—' }}</td>
                                    <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.created_at) }}</td>
                                    <td class="px-2 py-1.5 text-stone-600 dark:text-zinc-300">{{ formatDateTime(order.paid_at) }}</td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>

                            <p v-else class="text-xs text-stone-500 dark:text-zinc-400">No orders</p>
                          </div>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                  </table>
                </div>
              </div>
              <div class="flex items-center justify-end gap-2 border-t border-stone-300/80 px-3 py-2 sm:px-4 dark:border-zinc-700/60">
                <Button size="sm" variant="secondary" :disabled="page <= 1" @click="prevPage">Prev</Button>
                <Button size="sm" variant="secondary" :disabled="!usersData || page * pageSize >= usersData.total" @click="nextPage">Next</Button>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="providers" class="space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
              <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Providers</h2>
              <Button size="sm" @click="newProvider">New Provider</Button>
            </div>

            <Card v-if="showProviderForm" class="space-y-3">
              <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Provider Settings</h3>
              <div class="grid gap-2 md:grid-cols-2">
                <Input v-model="providerForm.name" placeholder="Name" />
                <div class="space-y-1">
                  <Input
                    v-model="providerForm.provider"
                    list="provider-type-options"
                    placeholder="Provider type (e.g. openai_compatible)"
                  />
                  <datalist id="provider-type-options">
                    <option v-for="item in providerTypeOptions" :key="item" :value="item" />
                  </datalist>
                </div>
                <Input v-model="providerForm.api_key" type="password" placeholder="API key" />
                <Input v-model="providerForm.base_url" placeholder="Base URL" />
                <Input v-model.number="providerForm.priority" type="number" placeholder="Priority" />
                <label class="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  <Checkbox v-model="providerForm.is_active" />
                  Active
                </label>
              </div>
              <div class="flex justify-end gap-2">
                <Button size="sm" variant="secondary" @click="showProviderForm = false">Cancel</Button>
                <Button size="sm" @click="saveProvider">Save</Button>
              </div>
            </Card>

            <Card :padding="false">
              <div class="py-3 sm:py-4">
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                  <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                    <tr class="border-b border-stone-300 dark:border-zinc-700">
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Name</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Type</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Base URL</th>
                      <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="p in providers"
                      :key="p.id"
                      class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                    >
                      <td class="px-3 py-2 text-stone-700 dark:text-zinc-200">{{ p.name }}</td>
                      <td class="px-3 py-2 font-mono text-xs text-stone-600 dark:text-zinc-300">{{ p.provider }}</td>
                      <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ p.base_url || '—' }}</td>
                      <td class="px-3 py-2 text-right">
                        <div class="flex flex-wrap justify-end gap-2">
                          <Button size="sm" variant="secondary" @click="editProvider(p)">Edit</Button>
                          <Button size="sm" variant="danger" @click="removeProvider(p.id)">Delete</Button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                  </table>
                </div>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="models" class="space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
              <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Models & Pricing</h2>
              <div class="flex flex-wrap items-center gap-2 sm:flex-nowrap">
                <span class="text-xs text-stone-500 dark:text-zinc-400">Token 计费单位固定为 1M</span>
                <Button size="sm" @click="openModelForm">Add Model</Button>
              </div>
            </div>

            <Card v-if="showModelForm" class="space-y-3">
              <div class="grid gap-2 md:grid-cols-4">
                <Select v-model="providerModelProviderId" class="md:col-span-2">
                  <option value="">Select provider</option>
                  <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
                </Select>
                <Select v-model="providerModelFormKind">
                  <option value="chat">LLM</option>
                  <option value="embedding">Embedding</option>
                </Select>
                <div class="flex gap-2">
                  <Button size="sm" variant="secondary" class="flex-1" @click="refreshDiscover(providerModelFormKind, false)">Discover</Button>
                  <Button size="sm" class="flex-1" @click="refreshDiscover(providerModelFormKind, true)">Import</Button>
                </div>
              </div>

              <div class="grid gap-2 md:grid-cols-3">
                <div class="flex gap-2 md:col-span-2">
                  <Select v-model="discoveredModelForCurrentKind" class="flex-1">
                    <option value="">Select discovered</option>
                    <option v-for="m in discoveredModelsForCurrentKind" :key="m" :value="m">{{ m }}</option>
                  </Select>
                  <Button size="sm" variant="secondary" @click="addModelDiscoveredByKind">
                    {{ providerModelFormKind === 'embedding' ? 'Add Embedding' : 'Add Model' }}
                  </Button>
                </div>
                <div class="flex gap-2">
                  <Input
                    v-model="providerModelManualInput"
                    class="flex-1"
                    :placeholder="providerModelFormKind === 'embedding' ? 'Manual embedding model id' : 'Manual model id'"
                  />
                  <Button size="sm" variant="secondary" @click="addModelManualByKind">
                    {{ providerModelFormKind === 'embedding' ? 'Add Embedding' : 'Add Model' }}
                  </Button>
                </div>
              </div>

              <Alert v-if="providerModelErrorForCurrentKind" variant="destructive">{{ providerModelErrorForCurrentKind }}</Alert>
              <Alert v-if="providerModelMessageForCurrentKind" variant="success">{{ providerModelMessageForCurrentKind }}</Alert>

              <div class="flex justify-end">
                <Button size="sm" variant="secondary" @click="closeModelForm">Close</Button>
              </div>
            </Card>

            <Card v-if="showPricingForm" class="space-y-3">
              <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">Pricing Rule</h3>
              <div class="grid gap-2 md:grid-cols-2">
                <Input list="known-models" v-model="pricingForm.model" placeholder="Model" />
                <Select v-model="pricingForm.billing_mode">
                  <option value="TOKEN">TOKEN</option>
                  <option value="REQUEST">REQUEST</option>
                </Select>

                <template v-if="pricingForm.billing_mode === 'TOKEN'">
                  <Input v-model.number="pricingForm.input_price" type="number" min="0" step="0.000001" placeholder="Input Price" />
                  <Input v-model.number="pricingForm.output_price" type="number" min="0" step="0.000001" placeholder="Output Price" />
                  <div class="rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-600 md:col-span-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    Token Unit: 1,000,000 (fixed)
                  </div>
                </template>

                <Input
                  v-else
                  v-model.number="pricingForm.request_price"
                  type="number"
                  min="0"
                  step="0.000001"
                  class="md:col-span-2"
                  placeholder="Price Per Request"
                />

                <label class="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 md:col-span-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  <Checkbox v-model="pricingForm.is_active" />
                  Active
                </label>
              </div>

              <datalist id="known-models">
                <option v-for="m in knownModels" :key="m" :value="m">{{ m }}</option>
              </datalist>

              <Alert v-if="pricingFormError" variant="destructive">{{ pricingFormError }}</Alert>

              <div class="flex justify-end gap-2">
                <Button size="sm" variant="secondary" @click="showPricingForm = false">Cancel</Button>
                <Button size="sm" @click="savePricing">Save</Button>
              </div>
            </Card>

            <Card :padding="false">
              <div class="py-3 sm:py-4">
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                  <thead class="bg-stone-100/80 dark:bg-zinc-800/60">
                    <tr class="border-b border-stone-300 dark:border-zinc-700">
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Model</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Provider</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Type</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Mode</th>
                      <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Pricing</th>
                      <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-zinc-400">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="model in knownModels"
                      :key="model"
                      class="border-b border-stone-200/80 transition-colors hover:bg-stone-100/70 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                    >
                      <td class="px-3 py-2 font-mono text-xs text-stone-700 dark:text-zinc-200">{{ model }}</td>
                      <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ providerNameForModel(model) }}</td>
                      <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ modelTypeForModel(model) }}</td>
                      <td class="px-3 py-2">
                        <span class="inline-flex rounded-full border border-stone-300 bg-stone-100 px-2 py-0.5 text-xs text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                          {{ pricingByModel(model)?.billing_mode || 'N/A' }}
                        </span>
                      </td>
                      <td class="px-3 py-2 text-stone-600 dark:text-zinc-300">{{ formatPricing(pricingByModel(model)) }}</td>
                      <td class="px-3 py-2 text-right">
                        <div class="flex flex-wrap justify-end gap-2">
                          <Button size="sm" variant="secondary" @click="pricingByModel(model) ? editPricing(pricingByModel(model)!) : newPricing(model)">
                            {{ pricingByModel(model) ? 'Edit' : 'Set' }}
                          </Button>
                          <Button size="sm" variant="danger" @click="removeModel(model)">Delete</Button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                  </table>
                </div>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="advanced" class="space-y-4">
            <div>
              <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">Advanced Settings</h2>
              <p class="text-xs text-stone-500 dark:text-zinc-400">LLM 请求与 OASIS 高级参数配置</p>
            </div>

            <Card class="space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
                <div>
                  <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">LLM Request Config</h3>
                  <p class="text-xs text-stone-500 dark:text-zinc-400">配置请求超时、重试次数和重试间隔</p>
                </div>
                <Button size="sm" variant="secondary" @click="reloadLlmRequestConfig">Refresh</Button>
              </div>

              <div class="grid gap-2 md:grid-cols-3">
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">llm_request_timeout_seconds</label>
                  <Input v-model.number="oasisConfig.llm_request_timeout_seconds" type="number" min="5" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">llm_retry_count</label>
                  <Input v-model.number="oasisConfig.llm_retry_count" type="number" min="0" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">llm_retry_interval_seconds</label>
                  <Input v-model.number="oasisConfig.llm_retry_interval_seconds" type="number" min="0" step="0.1" />
                </div>
              </div>

              <Alert v-if="llmRequestConfigError" variant="destructive">{{ llmRequestConfigError }}</Alert>
              <Alert v-if="llmRequestConfigMessage" variant="success">{{ llmRequestConfigMessage }}</Alert>

              <div class="flex justify-end">
                <Button size="sm" @click="saveLlmRequestConfig">Save LLM Request Config</Button>
              </div>
            </Card>

            <Card class="space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
                <div>
                  <h3 class="text-sm font-medium text-stone-700 dark:text-zinc-200">OASIS Advanced Config</h3>
                  <p class="text-xs text-stone-500 dark:text-zinc-400">配置分析/模拟/报告前缀与运行上限</p>
                </div>
                <Button size="sm" variant="secondary" @click="reloadOasisAdvancedConfig">Refresh</Button>
              </div>

              <div class="grid gap-2 md:grid-cols-2">
                <div class="space-y-1 md:col-span-2">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">analysis prompt prefix</label>
                  <Textarea
                    v-model="oasisConfig.analysis_prompt_prefix"
                    :rows="3"
                    placeholder="analysis prompt prefix"
                  />
                </div>
                <div class="space-y-1 md:col-span-2">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">simulation prompt prefix</label>
                  <Textarea
                    v-model="oasisConfig.simulation_prompt_prefix"
                    :rows="3"
                    placeholder="simulation prompt prefix"
                  />
                </div>
                <div class="space-y-1 md:col-span-2">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">report prompt prefix</label>
                  <Textarea
                    v-model="oasisConfig.report_prompt_prefix"
                    :rows="3"
                    placeholder="report prompt prefix"
                  />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_agent_profiles</label>
                  <Input v-model.number="oasisConfig.max_agent_profiles" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_events</label>
                  <Input v-model.number="oasisConfig.max_events" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_agent_activity</label>
                  <Input v-model.number="oasisConfig.max_agent_activity" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">min_total_hours</label>
                  <Input v-model.number="oasisConfig.min_total_hours" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_total_hours</label>
                  <Input v-model.number="oasisConfig.max_total_hours" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">min_minutes_per_round</label>
                  <Input v-model.number="oasisConfig.min_minutes_per_round" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_minutes_per_round</label>
                  <Input v-model.number="oasisConfig.max_minutes_per_round" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_posts_per_hour</label>
                  <Input v-model.number="oasisConfig.max_posts_per_hour" type="number" min="0.2" step="0.1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">max_response_delay_minutes</label>
                  <Input v-model.number="oasisConfig.max_response_delay_minutes" type="number" min="1" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-stone-500 dark:text-zinc-400">allowed_platforms (comma separated)</label>
                  <Input v-model="oasisAllowedPlatformsInput" placeholder="weibo, x, reddit" />
                </div>
              </div>

              <Alert v-if="oasisAdvancedConfigError" variant="destructive">{{ oasisAdvancedConfigError }}</Alert>
              <Alert v-if="oasisAdvancedConfigMessage" variant="success">{{ oasisAdvancedConfigMessage }}</Alert>

              <div class="flex justify-end">
                <Button size="sm" @click="saveOasisAdvancedConfig">Save OASIS Config</Button>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="payments" class="space-y-4">
            <div>
              <h2 class="text-base font-semibold text-stone-800 dark:text-zinc-100">EPay Config</h2>
              <p class="text-xs text-stone-500 dark:text-zinc-400">管理充值支付渠道参数</p>
            </div>

            <Card class="space-y-3">
              <div class="grid gap-2 md:grid-cols-2">
                <label class="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  <Checkbox v-model="paymentConfig.enabled" />
                  Enable EPay
                </label>
                <Select v-model="paymentConfig.payment_type">
                  <option value="alipay">alipay</option>
                  <option value="wxpay">wxpay</option>
                  <option value="qqpay">qqpay</option>
                </Select>
                <Input v-model="paymentConfig.url" placeholder="Gateway URL (https://...)" />
                <Input v-model="paymentConfig.pid" placeholder="Merchant PID" />
                <Input
                  v-model="paymentKeyInput"
                  type="password"
                  :placeholder="paymentConfig.has_key ? 'Key already set, leave blank to keep' : 'Communication key'"
                />
                <Input v-model="paymentConfig.notify_url" placeholder="Notify URL (optional)" />
                <Input v-model="paymentConfig.return_url" class="md:col-span-2" placeholder="Return URL (optional)" />
              </div>
              <div class="flex justify-end">
                <Button size="sm" @click="savePayment">Save</Button>
              </div>
            </Card>
          </TabsContent>
        </template>
      </Tabs>
    </div>
  </AdminLayout>
</template>
