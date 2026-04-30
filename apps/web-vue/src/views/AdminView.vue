<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import {
  BarChart3,
  BrainCircuit,
  CreditCard,
  ListChecks,
  PlugZap,
  SlidersHorizontal,
  Users,
} from 'lucide-vue-next'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import AdminTasksTab from '@/components/admin/AdminTasksTab.vue'
import AdminOverviewTab from '@/components/admin/AdminOverviewTab.vue'
import AdminUsersTab from '@/components/admin/AdminUsersTab.vue'
import AdminProvidersTab from '@/components/admin/AdminProvidersTab.vue'
import AdminModelsTab from '@/components/admin/AdminModelsTab.vue'
import AdminAdvancedTab from '@/components/admin/AdminAdvancedTab.vue'
import AdminPaymentsTab from '@/components/admin/AdminPaymentsTab.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  getStats, getUsers, createUser, updateUser, deleteUser, addUserBalance,
  getProviders, createProvider, updateProvider, deleteProvider,
  discoverProviderModels, discoverProviderEmbeddingModels, discoverProviderRerankerModels,
  addProviderModel, removeProviderModel,
  addProviderEmbeddingModel, removeProviderEmbeddingModel,
  addProviderRerankerModel, removeProviderRerankerModel,
  getPricing, createPricing, updatePricing,
  getPaymentConfig, updatePaymentConfig,
  getOasisConfig, updateOasisConfig,
  getUserOrders,
  getAdminTasks,
  cancelAdminTask,
} from '@/api/admin'
import type {
  AdminTask,
  AdminUser,
  OasisConfig,
  PaymentConfig,
  PaymentOrderListResponse,
  PricingRule,
  Provider,
  StatsResponse,
  UserListResponse,
} from '@/types'

type Tab = 'overview' | 'users' | 'providers' | 'models' | 'advanced' | 'payments' | 'tasks'
type UserStatus = '' | 'ACTIVE' | 'SUSPENDED' | 'DELETED'
type UserAdminFilter = '' | 'true' | 'false'
type AdminTaskStatusFilter = '' | 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
type ProviderModelKind = 'chat' | 'embedding' | 'reranker'
type ModelRow = {
  providerId: string
  providerName: string
  kind: ProviderModelKind
  model: string
}
type AdminTaskFilters = {
  status: AdminTaskStatusFilter
  task_type: string
  project_id: string
  user_id: string
  limit: number
}

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
  provider: '',
  api_key: '',
  base_url: '',
  is_active: true,
  priority: 0,
})
const showProviderForm = ref(false)
const providerTypeOptions = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic_compatible', label: 'Anthropic Compatible' },
]

const providerModelProviderId = ref('')
const providerModelFormKind = ref<'chat' | 'embedding' | 'reranker'>('chat')
const providerModelManualInput = ref('')
const discoveredProviderModels = ref<string[]>([])
const discoveredProviderModel = ref('')
const providerModelMessage = ref('')
const providerModelError = ref('')
const discoveredProviderEmbeddingModels = ref<string[]>([])
const discoveredProviderEmbeddingModel = ref('')
const providerEmbeddingMessage = ref('')
const providerEmbeddingError = ref('')
const discoveredProviderRerankerModels = ref<string[]>([])
const discoveredProviderRerankerModel = ref('')
const providerRerankerMessage = ref('')
const providerRerankerError = ref('')
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
  max_actions_per_hour: 20,
  max_response_delay_minutes: 720,
  llm_request_timeout_seconds: 180,
  llm_retry_count: 4,
  llm_retry_interval_seconds: 2,
  llm_prefer_stream: true,
  llm_stream_fallback_nonstream: true,
  llm_openai_api_style: 'responses',
  llm_reasoning_effort: 'model_default',
  llm_task_concurrency: 4,
  llm_model_default_concurrency: 8,
  llm_model_concurrency_overrides: {},
  graphiti_chunk_size: 4000,
  graphiti_chunk_overlap: 160,
  graphiti_llm_max_tokens: 16384,
})
const llmModelConcurrencyOverridesInput = ref('{}')
const llmRequestConfigMessage = ref('')
const llmRequestConfigError = ref('')
const oasisAdvancedConfigMessage = ref('')
const oasisAdvancedConfigError = ref('')

const expandedUserOrdersId = ref<string | null>(null)
const userOrdersLoading = ref(false)
const userOrdersError = ref('')
const userOrdersData = ref<PaymentOrderListResponse | null>(null)
const adminTasks = ref<AdminTask[]>([])
const adminTasksTotal = ref(0)
const adminTasksLoading = ref(false)
const adminTasksError = ref('')
const adminTasksMessage = ref('')
const adminTaskFilters = ref<AdminTaskFilters>({
  status: '',
  task_type: '',
  project_id: '',
  user_id: '',
  limit: 200,
})
const adminCancellingTaskIds = ref<string[]>([])

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
  { value: 'overview', label: 'Overview', icon: BarChart3, hint: 'System stats' },
  { value: 'users', label: 'Users', icon: Users, hint: 'User management' },
  { value: 'providers', label: 'Providers', icon: PlugZap, hint: 'Provider setup' },
  { value: 'models', label: 'Models', icon: BrainCircuit, hint: 'Models and pricing' },
  { value: 'advanced', label: 'Advanced', icon: SlidersHorizontal, hint: 'Runtime settings' },
  { value: 'payments', label: 'Payments', icon: CreditCard, hint: 'Payment gateway' },
  { value: 'tasks', label: 'Tasks', icon: ListChecks, hint: 'Task monitoring' },
]

const discoveredModelsForCurrentKind = computed(() => {
  if (providerModelFormKind.value === 'reranker') return discoveredProviderRerankerModels.value
  if (providerModelFormKind.value === 'embedding') return discoveredProviderEmbeddingModels.value
  return discoveredProviderModels.value
})
const discoveredModelForCurrentKind = computed({
  get: () => {
    if (providerModelFormKind.value === 'reranker') return discoveredProviderRerankerModel.value
    if (providerModelFormKind.value === 'embedding') return discoveredProviderEmbeddingModel.value
    return discoveredProviderModel.value
  },
  set: (value: string) => {
    if (providerModelFormKind.value === 'reranker') {
      discoveredProviderRerankerModel.value = value
      return
    }
    if (providerModelFormKind.value === 'embedding') {
      discoveredProviderEmbeddingModel.value = value
      return
    }
    discoveredProviderModel.value = value
  },
})
const providerModelMessageForCurrentKind = computed(() => {
  if (providerModelFormKind.value === 'reranker') return providerRerankerMessage.value
  if (providerModelFormKind.value === 'embedding') return providerEmbeddingMessage.value
  return providerModelMessage.value
})
const providerModelErrorForCurrentKind = computed(() => {
  if (providerModelFormKind.value === 'reranker') return providerRerankerError.value
  if (providerModelFormKind.value === 'embedding') return providerEmbeddingError.value
  return providerModelError.value
})
const knownModels = computed(() =>
  Array.from(
    new Set([
      ...providers.value.flatMap((p) => p.models || []),
      ...providers.value.flatMap((p) => p.embedding_models || []),
      ...providers.value.flatMap((p) => p.reranker_models || []),
    ])
  ).sort()
)
const totalKnownModels = computed(() => knownModels.value.length)

const modelRows = computed<ModelRow[]>(() => {
  const rows: ModelRow[] = []
  for (const provider of providers.value) {
    for (const model of provider.models || []) {
      rows.push({ providerId: provider.id, providerName: provider.name, kind: 'chat', model })
    }
    for (const model of provider.embedding_models || []) {
      rows.push({ providerId: provider.id, providerName: provider.name, kind: 'embedding', model })
    }
    for (const model of provider.reranker_models || []) {
      rows.push({ providerId: provider.id, providerName: provider.name, kind: 'reranker', model })
    }
  }
  return rows.sort((a, b) =>
    a.model.localeCompare(b.model) || a.providerName.localeCompare(b.providerName) || a.kind.localeCompare(b.kind)
  )
})

function formatModelConcurrencyOverrides(overrides: Record<string, number>): string {
  const normalized: Record<string, number> = {}
  const rows: Array<[string, number]> = []
  for (const [rawKey, rawValue] of Object.entries(overrides || {})) {
    const key = String(rawKey || '').trim().toLowerCase()
    const value = Number(rawValue)
    if (!key || !Number.isFinite(value) || value < 1) continue
    rows.push([key, value])
  }
  rows.sort((a, b) => a[0].localeCompare(b[0]))
  for (const [key, value] of rows) {
    normalized[key] = value
  }
  return JSON.stringify(normalized, null, 2)
}

function parseModelConcurrencyOverrides(raw: string): Record<string, number> {
  const text = String(raw || '').trim()
  if (!text) return {}
  let payload: unknown
  try {
    payload = JSON.parse(text)
  } catch (error: unknown) {
    throw new Error('llm_model_concurrency_overrides must be valid JSON')
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('llm_model_concurrency_overrides must be a JSON object, for example {"your-model-id": 4}')
  }
  const normalized: Record<string, number> = {}
  for (const [rawKey, rawValue] of Object.entries(payload as Record<string, unknown>)) {
    const key = String(rawKey || '').trim().toLowerCase()
    const value = Number(rawValue)
    if (!key || !Number.isFinite(value) || value < 1) continue
    normalized[key] = value
  }
  return normalized
}

function pricingByModel(model: string): PricingRule | undefined {
  return pricingRules.value.find((r) => r.model === model)
}

function formatPricing(rule?: PricingRule): string {
  if (!rule) return 'Not configured'
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

function updateAdminTaskFilters(next: AdminTaskFilters) {
  adminTaskFilters.value = next
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
    getOasisConfig()
      .then((d) => {
        oasisConfig.value = d
        llmModelConcurrencyOverridesInput.value = formatModelConcurrencyOverrides(
          d.llm_model_concurrency_overrides || {}
        )
      })
      .catch(() => {}),
    getAdminTasks({ limit: adminTaskFilters.value.limit })
      .then((d) => {
        adminTasks.value = d.tasks || []
        adminTasksTotal.value = Number(d.total || 0)
      })
      .catch(() => {}),
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
  providerForm.value = {
    id: '',
    name: '',
    provider: 'openai_compatible',
    api_key: '',
    base_url: '',
    is_active: true,
    priority: 0,
  }
  showProviderForm.value = true
}

async function saveProvider() {
  const providerType = providerForm.value.provider.trim()
  if (!providerForm.value.name.trim()) {
    window.alert('Provider name is required')
    return
  }
  if (!providerType) {
    window.alert('Provider type is required')
    return
  }
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
  pricingRules.value = await getPricing()
}

type ProviderModelAction = 'add' | 'remove'

function clearProviderModelFeedback(kind: ProviderModelKind) {
  if (kind === 'reranker') {
    providerRerankerError.value = ''
    providerRerankerMessage.value = ''
    return
  }
  if (kind === 'embedding') {
    providerEmbeddingError.value = ''
    providerEmbeddingMessage.value = ''
    return
  }
  providerModelError.value = ''
  providerModelMessage.value = ''
}

function setProviderModelMessage(kind: ProviderModelKind, message: string) {
  if (kind === 'reranker') {
    providerRerankerMessage.value = message
    return
  }
  if (kind === 'embedding') {
    providerEmbeddingMessage.value = message
    return
  }
  providerModelMessage.value = message
}

function setProviderModelError(kind: ProviderModelKind, message: string) {
  if (kind === 'reranker') {
    providerRerankerError.value = message
    return
  }
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
    if (kind === 'reranker') {
      const discovered = await discoverProviderRerankerModels(providerModelProviderId.value, persist)
      discoveredProviderRerankerModels.value = discovered.discovered
      discoveredProviderRerankerModel.value = discovered.discovered[0] || ''
      if (persist) await refreshProviders()
      setProviderModelMessage(kind, `${persist ? 'Imported' : 'Discovered'} ${discovered.discovered.length}`)
      return
    }
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
    if (kind === 'reranker') {
      next = action === 'add'
        ? await addProviderRerankerModel(providerModelProviderId.value, modelId)
        : await removeProviderRerankerModel(providerModelProviderId.value, modelId)
      setProviderModelMessage(kind, `Reranker models: ${next.length}`)
    } else if (kind === 'embedding') {
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
    const kindLabel = kind === 'embedding' ? 'embedding model' : kind === 'reranker' ? 'reranker model' : 'model'
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
  discoveredProviderRerankerModel.value = ''
  discoveredProviderRerankerModels.value = []
}

function openModelForm() {
  providerModelFormKind.value = 'chat'
  resetModelDiscoverState()
  providerModelError.value = ''
  providerModelMessage.value = ''
  providerEmbeddingError.value = ''
  providerEmbeddingMessage.value = ''
  providerRerankerError.value = ''
  providerRerankerMessage.value = ''
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
  providerRerankerError.value = ''
  providerRerankerMessage.value = ''
}

watch(providerModelProviderId, () => {
  resetModelDiscoverState()
  providerModelManualInput.value = ''
  clearProviderModelFeedback('chat')
  clearProviderModelFeedback('embedding')
  clearProviderModelFeedback('reranker')
})

watch(providerModelFormKind, () => {
  providerModelManualInput.value = ''
  clearProviderModelFeedback('chat')
  clearProviderModelFeedback('embedding')
  clearProviderModelFeedback('reranker')
})

function applyLlmRequestFields(next: OasisConfig) {
  oasisConfig.value.llm_request_timeout_seconds = next.llm_request_timeout_seconds
  oasisConfig.value.llm_retry_count = next.llm_retry_count
  oasisConfig.value.llm_retry_interval_seconds = next.llm_retry_interval_seconds
  oasisConfig.value.llm_prefer_stream = next.llm_prefer_stream
  oasisConfig.value.llm_stream_fallback_nonstream = next.llm_stream_fallback_nonstream
  oasisConfig.value.llm_openai_api_style = next.llm_openai_api_style
  oasisConfig.value.llm_reasoning_effort = next.llm_reasoning_effort
  oasisConfig.value.llm_task_concurrency = next.llm_task_concurrency
  oasisConfig.value.llm_model_default_concurrency = next.llm_model_default_concurrency
  oasisConfig.value.llm_model_concurrency_overrides = { ...next.llm_model_concurrency_overrides }
  oasisConfig.value.graphiti_chunk_size = next.graphiti_chunk_size
  oasisConfig.value.graphiti_chunk_overlap = next.graphiti_chunk_overlap
  oasisConfig.value.graphiti_llm_max_tokens = next.graphiti_llm_max_tokens
  llmModelConcurrencyOverridesInput.value = formatModelConcurrencyOverrides(
    next.llm_model_concurrency_overrides || {}
  )
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
  oasisConfig.value.max_actions_per_hour = next.max_actions_per_hour
  oasisConfig.value.max_response_delay_minutes = next.max_response_delay_minutes
}

async function saveLlmRequestConfig() {
  llmRequestConfigError.value = ''
  llmRequestConfigMessage.value = ''
  try {
    const modelOverrides = parseModelConcurrencyOverrides(llmModelConcurrencyOverridesInput.value)
    const updated = await updateOasisConfig({
      llm_request_timeout_seconds: Number(oasisConfig.value.llm_request_timeout_seconds || 0),
      llm_retry_count: Number(oasisConfig.value.llm_retry_count || 0),
      llm_retry_interval_seconds: Number(oasisConfig.value.llm_retry_interval_seconds || 0),
      llm_prefer_stream: Boolean(oasisConfig.value.llm_prefer_stream),
      llm_stream_fallback_nonstream: Boolean(oasisConfig.value.llm_stream_fallback_nonstream),
      llm_openai_api_style: String(oasisConfig.value.llm_openai_api_style || 'responses'),
      llm_reasoning_effort: String(oasisConfig.value.llm_reasoning_effort || 'model_default'),
      llm_task_concurrency: Number(oasisConfig.value.llm_task_concurrency || 0),
      llm_model_default_concurrency: Number(oasisConfig.value.llm_model_default_concurrency || 0),
      llm_model_concurrency_overrides: modelOverrides,
      graphiti_chunk_size: Number(oasisConfig.value.graphiti_chunk_size || 0),
      graphiti_chunk_overlap: Number(oasisConfig.value.graphiti_chunk_overlap || 0),
      graphiti_llm_max_tokens: Number(oasisConfig.value.graphiti_llm_max_tokens || 0),
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
      max_actions_per_hour: Number(oasisConfig.value.max_actions_per_hour || 0),
      max_response_delay_minutes: Number(oasisConfig.value.max_response_delay_minutes || 0),
    })
    applyOasisAdvancedFields(updated)
    oasisAdvancedConfigMessage.value = 'Scenario reasoning config updated'
  } catch (error: unknown) {
    oasisAdvancedConfigError.value = getErrorMessage(error, 'Save scenario reasoning config failed')
  }
}

async function reloadOasisAdvancedConfig() {
  oasisAdvancedConfigError.value = ''
  oasisAdvancedConfigMessage.value = ''
  try {
    const latest = await getOasisConfig()
    applyOasisAdvancedFields(latest)
    oasisAdvancedConfigMessage.value = 'Scenario reasoning config refreshed'
  } catch (error: unknown) {
    oasisAdvancedConfigError.value = getErrorMessage(error, 'Load scenario reasoning config failed')
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

async function loadAdminTasks() {
  adminTasksError.value = ''
  adminTasksMessage.value = ''
  adminTasksLoading.value = true
  try {
    const response = await getAdminTasks({
      status: adminTaskFilters.value.status || undefined,
      task_type: adminTaskFilters.value.task_type.trim() || undefined,
      project_id: adminTaskFilters.value.project_id.trim() || undefined,
      user_id: adminTaskFilters.value.user_id.trim() || undefined,
      limit: Number(adminTaskFilters.value.limit || 200),
    })
    adminTasks.value = response.tasks || []
    adminTasksTotal.value = Number(response.total || 0)
    adminTasksMessage.value = 'Task list refreshed'
  } catch (error: unknown) {
    adminTasksError.value = getErrorMessage(error, 'Load tasks failed')
  } finally {
    adminTasksLoading.value = false
  }
}

async function cancelTaskByAdmin(task: AdminTask) {
  const status = String(task?.status || '').toLowerCase()
  if (!task?.task_id || (status !== 'pending' && status !== 'processing')) return
  if (adminCancellingTaskIds.value.includes(task.task_id)) return
  adminTasksError.value = ''
  adminTasksMessage.value = ''
  adminCancellingTaskIds.value = [...adminCancellingTaskIds.value, task.task_id]
  try {
    const latest = await cancelAdminTask(task.task_id)
    adminTasks.value = adminTasks.value.map((item) => (item.task_id === latest.task_id ? latest : item))
    adminTasksMessage.value = `Task ${task.task_id} cancelled`
  } catch (error: unknown) {
    adminTasksError.value = getErrorMessage(error, 'Cancel task failed')
  } finally {
    adminCancellingTaskIds.value = adminCancellingTaskIds.value.filter((id) => id !== task.task_id)
  }
}

async function removeModelBinding(row: ModelRow) {
  const confirmed = window.confirm(
    `Remove ${row.kind} model "${row.model}" from provider "${row.providerName}"?`
  )
  if (!confirmed) return

  if (row.kind === 'reranker') {
    await removeProviderRerankerModel(row.providerId, row.model)
  } else if (row.kind === 'embedding') {
    await removeProviderEmbeddingModel(row.providerId, row.model)
  } else {
    await removeProviderModel(row.providerId, row.model)
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

  await refreshProviders()
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
    <div class="muse-page-shell muse-page-shell-wide">
      <section class="muse-page-header">
        <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div class="space-y-1">
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Admin Panel</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400">Manage users, providers, pricing, payment settings, and runtime controls.</p>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
            <div class="rounded-md border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Providers</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ providers.length }}</p>
            </div>
            <div class="rounded-md border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Models</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ totalKnownModels }}</p>
            </div>
            <div class="rounded-md border border-stone-300/70 bg-stone-100/80 px-3 py-2 text-stone-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-500">Pricing Rules</p>
              <p class="mt-0.5 text-sm font-semibold text-stone-700 dark:text-zinc-100">{{ pricingRules.length }}</p>
            </div>
          </div>
        </div>
      </section>

      <Tabs v-model="tab" class="space-y-4">
        <div class="muse-surface rounded-md p-1">
          <TabsList class="grid h-auto w-full grid-cols-2 gap-1 bg-transparent p-0 md:grid-cols-6">
            <TabsTrigger
              v-for="item in tabItems"
              :key="item.value"
              :value="item.value"
              class="h-auto rounded-md py-2"
            >
              <component :is="item.icon" class="h-3.5 w-3.5" />
              <span>{{ item.label }}</span>
              <span class="hidden text-[10px] text-stone-500 dark:text-zinc-400 md:inline">{{ item.hint }}</span>
            </TabsTrigger>
          </TabsList>
        </div>

        <Card v-if="loading">
          <p class="text-sm text-stone-600 dark:text-zinc-300">Loading admin data...</p>
        </Card>

        <template v-else>
          <TabsContent value="overview" class="space-y-4">
            <AdminOverviewTab
              :stats="stats"
              :format-currency="formatCurrency"
              :format-tokens="formatTokens"
            />
          </TabsContent>

          <TabsContent value="users" class="space-y-4">
            <AdminUsersTab
              :users-data="usersData"
              :show-user-form="showUserForm"
              :user-filters="userFilters"
              :user-form="userForm"
              :row-balance-input="rowBalanceInput"
              :page="page"
              :page-size="pageSize"
              :expanded-user-orders-id="expandedUserOrdersId"
              :user-orders-loading="userOrdersLoading"
              :user-orders-error="userOrdersError"
              :user-orders-data="userOrdersData"
              :status-chip-class="statusChipClass"
              :order-status-chip-class="orderStatusChipClass"
              :format-tokens="formatTokens"
              :format-currency="formatCurrency"
              :format-date-time="formatDateTime"
              :get-user-token-usage="getUserTokenUsage"
              :get-user-recharge-summary="getUserRechargeSummary"
              @open-user-form="showUserForm = true"
              @close-user-form="showUserForm = false"
              @save-user="saveUser"
              @apply-user-filters="applyUserFilters"
              @reset-user-filters="resetUserFilters"
              @toggle-admin="toggleAdmin"
              @add-balance-for-user="addBalanceForUser"
              @toggle-user-orders="toggleUserOrders"
              @load-user-orders="loadUserOrders"
              @remove-user="removeUser"
              @prev-page="prevPage"
              @next-page="nextPage"
            />
          </TabsContent>

          <TabsContent value="providers" class="space-y-4">
            <AdminProvidersTab
              :providers="providers"
              :show-provider-form="showProviderForm"
              :provider-form="providerForm"
              :provider-type-options="providerTypeOptions"
              @new-provider="newProvider"
              @edit-provider="editProvider"
              @close-provider-form="showProviderForm = false"
              @save-provider="saveProvider"
              @remove-provider="removeProvider"
            />
          </TabsContent>

          <TabsContent value="models" class="space-y-4">
            <AdminModelsTab
              :providers="providers"
              :known-models="knownModels"
              :show-model-form="showModelForm"
              :provider-model-provider-id="providerModelProviderId"
              :provider-model-form-kind="providerModelFormKind"
              :provider-model-manual-input="providerModelManualInput"
              :discovered-models-for-current-kind="discoveredModelsForCurrentKind"
              :discovered-model-for-current-kind="discoveredModelForCurrentKind"
              :provider-model-error-for-current-kind="providerModelErrorForCurrentKind"
              :provider-model-message-for-current-kind="providerModelMessageForCurrentKind"
              :show-pricing-form="showPricingForm"
              :pricing-form="pricingForm"
              :pricing-form-error="pricingFormError"
              :format-pricing="formatPricing"
              :pricing-by-model="pricingByModel"
              :model-rows="modelRows"
              @open-model-form="openModelForm"
              @close-model-form="closeModelForm"
              @update:provider-model-provider-id="providerModelProviderId = $event"
              @update:provider-model-form-kind="providerModelFormKind = $event"
              @refresh-discover="refreshDiscover"
              @update:discovered-model-for-current-kind="discoveredModelForCurrentKind = $event"
              @add-model-discovered="addModelDiscoveredByKind"
              @update:provider-model-manual-input="providerModelManualInput = $event"
              @add-model-manual="addModelManualByKind"
              @remove-model-binding="removeModelBinding"
              @new-pricing="newPricing"
              @edit-pricing="editPricing"
              @update:show-pricing-form="showPricingForm = $event"
              @save-pricing="savePricing"
            />
          </TabsContent>

          <TabsContent value="advanced" class="space-y-4">
            <AdminAdvancedTab
              :oasis-config="oasisConfig"
              :llm-model-concurrency-overrides-input="llmModelConcurrencyOverridesInput"
              :llm-request-config-error="llmRequestConfigError"
              :llm-request-config-message="llmRequestConfigMessage"
              :oasis-advanced-config-error="oasisAdvancedConfigError"
              :oasis-advanced-config-message="oasisAdvancedConfigMessage"
              @reload-llm-request-config="reloadLlmRequestConfig"
              @save-llm-request-config="saveLlmRequestConfig"
              @reload-oasis-advanced-config="reloadOasisAdvancedConfig"
              @save-oasis-advanced-config="saveOasisAdvancedConfig"
              @update:llm-model-concurrency-overrides-input="llmModelConcurrencyOverridesInput = $event"
            />
          </TabsContent>

          <TabsContent value="payments" class="space-y-4">
            <AdminPaymentsTab
              :payment-config="paymentConfig"
              :payment-key-input="paymentKeyInput"
              @update:payment-key-input="paymentKeyInput = $event"
              @save-payment="savePayment"
            />
          </TabsContent>

          <TabsContent value="tasks">
            <AdminTasksTab
              :tasks="adminTasks"
              :total="adminTasksTotal"
              :loading="adminTasksLoading"
              :error="adminTasksError"
              :message="adminTasksMessage"
              :filters="adminTaskFilters"
              :cancelling-task-ids="adminCancellingTaskIds"
              :format-date-time="formatDateTime"
              @refresh="loadAdminTasks"
              @cancel="cancelTaskByAdmin"
              @update:filters="updateAdminTaskFilters"
            />
          </TabsContent>
        </template>
      </Tabs>
    </div>
  </AdminLayout>
</template>


