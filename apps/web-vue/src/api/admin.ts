import api from './index'
import type {
  AdminTask,
  AdminTaskListResponse,
  StatsResponse,
  UserListResponse,
  Provider,
  PricingRule,
  AdminUser,
  PaymentAdapterAdmin,
  PaymentAdapterTypeMeta,
  LlmRuntimeConfig,
  PaymentOrderListResponse,
  UsageRecordListResponse,
  UsageRetentionConfig,
} from '@/types'

type RawLlmRuntimeConfig = Partial<LlmRuntimeConfig>

interface ProviderMutationPayload {
  name: string
  provider: string
  api_key: string
  base_url?: string | null
  is_active?: boolean
  priority?: number
}

interface ProviderUpdatePayload {
  name?: string
  provider?: string
  api_key?: string
  base_url?: string | null
  is_active?: boolean
  priority?: number
}

interface ProviderModelListPayload {
  provider_id: string
  models?: string[]
  embedding_models?: string[]
  reranker_models?: string[]
}

type ProviderModelKind = 'chat' | 'embedding' | 'reranker'

function providerModelPath(providerId: string, kind: ProviderModelKind): string {
  if (kind === 'reranker') {
    return `/api/admin/providers/${providerId}/reranker-models`
  }
  return kind === 'embedding'
    ? `/api/admin/providers/${providerId}/embedding-models`
    : `/api/admin/providers/${providerId}/models`
}

function normalizeProviderModelList(payload: ProviderModelListPayload, kind: ProviderModelKind): string[] {
  if (kind === 'reranker') {
    return payload.reranker_models ?? payload.models ?? payload.embedding_models ?? []
  }
  return kind === 'embedding'
    ? (payload.embedding_models ?? payload.models ?? payload.reranker_models ?? [])
    : (payload.models ?? payload.embedding_models ?? payload.reranker_models ?? [])
}

export async function getStats(): Promise<StatsResponse> {
  const { data } = await api.get<StatsResponse>('/api/admin/stats')
  return data
}

export async function getAdminTasks(params?: {
  task_type?: string
  project_id?: string
  user_id?: string
  status?: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  limit?: number
}): Promise<AdminTaskListResponse> {
  const { data } = await api.get<AdminTaskListResponse>('/api/admin/tasks', { params: params || {} })
  return {
    tasks: Array.isArray(data.tasks) ? data.tasks : [],
    total: Number(data.total || 0),
    limit: Number(data.limit || 0),
  }
}

export async function cancelAdminTask(taskId: string): Promise<AdminTask> {
  const { data } = await api.post<{ task: AdminTask }>(`/api/admin/tasks/${taskId}/cancel`)
  return data.task
}

export async function getUsers(
  page = 1,
  pageSize = 20,
  filters?: {
    search?: string
    is_admin?: boolean
    status?: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  }
): Promise<UserListResponse> {
  const { data } = await api.get<UserListResponse>('/api/admin/users', {
    params: { page, page_size: pageSize, ...(filters || {}) },
  })
  return data
}

export async function createUser(payload: {
  email: string
  password: string
  nickname: string
  is_admin?: boolean
  status?: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  balance?: number
}): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>('/api/admin/users', payload)
  return data
}

export async function updateUser(userId: string, payload: {
  email?: string
  nickname?: string
  is_admin?: boolean
  status?: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  balance?: number
}): Promise<AdminUser> {
  const { data } = await api.put<AdminUser>(`/api/admin/users/${userId}`, payload)
  return data
}

export async function resetUserPassword(userId: string, password: string): Promise<void> {
  await api.post(`/api/admin/users/${userId}/password`, { password })
}

export async function deleteUser(userId: string): Promise<void> {
  await api.delete(`/api/admin/users/${userId}`)
}

export async function getProviders(): Promise<Provider[]> {
  const { data } = await api.get<Provider[]>('/api/admin/providers')
  return data
}

export async function createProvider(provider: ProviderMutationPayload): Promise<Provider> {
  const { data } = await api.post<Provider>('/api/admin/providers', provider)
  return data
}

export async function updateProvider(providerId: string, provider: ProviderUpdatePayload): Promise<Provider> {
  const { data } = await api.put<Provider>(`/api/admin/providers/${providerId}`, provider)
  return data
}

export async function deleteProvider(providerId: string): Promise<void> {
  await api.delete(`/api/admin/providers/${providerId}`)
}

export async function discoverProviderModels(providerId: string, persist = false): Promise<{ discovered: string[]; models: string[]; persisted: boolean }> {
  const { data } = await api.post<{ provider_id: string; provider_name: string; discovered: string[]; models: string[]; persisted: boolean }>(
    `${providerModelPath(providerId, 'chat')}/discover`,
    null,
    { params: { persist } },
  )
  return { discovered: data.discovered, models: data.models, persisted: data.persisted }
}

export async function discoverProviderEmbeddingModels(
  providerId: string,
  persist = false
): Promise<{ discovered: string[]; embedding_models: string[]; persisted: boolean }> {
  const { data } = await api.post<{ provider_id: string; provider_name: string; discovered: string[]; embedding_models?: string[]; models?: string[]; persisted: boolean }>(
    `${providerModelPath(providerId, 'embedding')}/discover`,
    null,
    { params: { persist } },
  )
  return {
    discovered: data.discovered,
    embedding_models: data.embedding_models ?? data.models ?? [],
    persisted: data.persisted,
  }
}

export async function discoverProviderRerankerModels(
  providerId: string,
  persist = false
): Promise<{ discovered: string[]; reranker_models: string[]; persisted: boolean }> {
  const { data } = await api.post<{ provider_id: string; provider_name: string; discovered: string[]; reranker_models?: string[]; models?: string[]; persisted: boolean }>(
    `${providerModelPath(providerId, 'reranker')}/discover`,
    null,
    { params: { persist } },
  )
  return {
    discovered: data.discovered,
    reranker_models: data.reranker_models ?? data.models ?? [],
    persisted: data.persisted,
  }
}

export async function addProviderModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.post<ProviderModelListPayload>(providerModelPath(providerId, 'chat'), { model })
  return normalizeProviderModelList(data, 'chat')
}

export async function removeProviderModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.delete<ProviderModelListPayload>(providerModelPath(providerId, 'chat'), {
    params: { model },
  })
  return normalizeProviderModelList(data, 'chat')
}

export async function addProviderEmbeddingModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.post<ProviderModelListPayload>(providerModelPath(providerId, 'embedding'), { model })
  return normalizeProviderModelList(data, 'embedding')
}

export async function removeProviderEmbeddingModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.delete<ProviderModelListPayload>(providerModelPath(providerId, 'embedding'), {
    params: { model },
  })
  return normalizeProviderModelList(data, 'embedding')
}

export async function addProviderRerankerModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.post<ProviderModelListPayload>(providerModelPath(providerId, 'reranker'), { model })
  return normalizeProviderModelList(data, 'reranker')
}

export async function removeProviderRerankerModel(providerId: string, model: string): Promise<string[]> {
  const { data } = await api.delete<ProviderModelListPayload>(providerModelPath(providerId, 'reranker'), {
    params: { model },
  })
  return normalizeProviderModelList(data, 'reranker')
}

export async function getPricing(): Promise<PricingRule[]> {
  const { data } = await api.get<PricingRule[]>('/api/admin/pricing')
  return data
}

export async function createPricing(payload: {
  model: string
  billing_mode: 'TOKEN' | 'REQUEST'
  input_price?: number
  output_price?: number
  token_unit?: number
  request_price?: number
  is_active?: boolean
}): Promise<PricingRule> {
  const { data } = await api.post<PricingRule>('/api/admin/pricing', payload)
  return data
}

export async function updatePricing(ruleId: string, payload: Partial<PricingRule>): Promise<PricingRule> {
  const { data } = await api.put<PricingRule>(`/api/admin/pricing/${ruleId}`, payload)
  return data
}

export async function getPaymentAdapterTypes(): Promise<PaymentAdapterTypeMeta[]> {
  const { data } = await api.get<{ types: PaymentAdapterTypeMeta[] }>('/api/admin/payment-adapter-types')
  return data.types || []
}

export async function getPaymentAdapters(): Promise<PaymentAdapterAdmin[]> {
  const { data } = await api.get<{ adapters: PaymentAdapterAdmin[] }>('/api/admin/payment-adapters')
  return data.adapters || []
}

export async function createPaymentAdapter(payload: {
  adapter_type: string
  display_name: string
  enabled?: boolean
  sort_order?: number
  config?: Record<string, unknown>
}): Promise<PaymentAdapterAdmin> {
  const { data } = await api.post<PaymentAdapterAdmin>('/api/admin/payment-adapters', payload)
  return data
}

export async function updatePaymentAdapter(
  adapterId: string,
  payload: {
    display_name?: string
    enabled?: boolean
    sort_order?: number
    config?: Record<string, unknown>
  },
): Promise<PaymentAdapterAdmin> {
  const { data } = await api.put<PaymentAdapterAdmin>(`/api/admin/payment-adapters/${adapterId}`, payload)
  return data
}

export async function deletePaymentAdapter(adapterId: string): Promise<void> {
  await api.delete(`/api/admin/payment-adapters/${adapterId}`)
}

const DEFAULT_LLM_RUNTIME_CONFIG: LlmRuntimeConfig = {
  llm_request_timeout_seconds: 180,
  llm_retry_count: 4,
  llm_retry_interval_seconds: 2,
  llm_prefer_stream: true,
  llm_stream_fallback_nonstream: true,
  llm_fallback_model: '',
  llm_openai_api_style: 'responses',
  llm_reasoning_effort: 'model_default',
  llm_task_concurrency: 4,
  llm_model_default_concurrency: 8,
  llm_model_concurrency_overrides: {},
}

function normalizeModelConcurrencyOverrides(raw: unknown): Record<string, number> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const normalized: Record<string, number> = {}
  for (const [rawKey, rawValue] of Object.entries(raw as Record<string, unknown>)) {
    const key = String(rawKey || '').trim().toLowerCase()
    const value = Number(rawValue)
    if (!key || !Number.isFinite(value) || value < 1) continue
    normalized[key] = value
  }
  return normalized
}

function normalizeLlmRuntimeConfig(payload: RawLlmRuntimeConfig | null | undefined): LlmRuntimeConfig {
  return {
    llm_request_timeout_seconds: Number(
      payload?.llm_request_timeout_seconds ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_request_timeout_seconds
    ),
    llm_retry_count: Number(payload?.llm_retry_count ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_retry_count),
    llm_retry_interval_seconds: Number(
      payload?.llm_retry_interval_seconds ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_retry_interval_seconds
    ),
    llm_prefer_stream:
      typeof payload?.llm_prefer_stream === 'boolean'
        ? payload.llm_prefer_stream
        : DEFAULT_LLM_RUNTIME_CONFIG.llm_prefer_stream,
    llm_stream_fallback_nonstream:
      typeof payload?.llm_stream_fallback_nonstream === 'boolean'
        ? payload.llm_stream_fallback_nonstream
        : DEFAULT_LLM_RUNTIME_CONFIG.llm_stream_fallback_nonstream,
    llm_fallback_model: String(payload?.llm_fallback_model ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_fallback_model),
    llm_openai_api_style:
      typeof payload?.llm_openai_api_style === 'string' && payload.llm_openai_api_style.trim()
        ? payload.llm_openai_api_style.trim()
        : DEFAULT_LLM_RUNTIME_CONFIG.llm_openai_api_style,
    llm_reasoning_effort:
      typeof payload?.llm_reasoning_effort === 'string' && payload.llm_reasoning_effort.trim()
        ? payload.llm_reasoning_effort.trim()
        : DEFAULT_LLM_RUNTIME_CONFIG.llm_reasoning_effort,
    llm_task_concurrency: Number(
      payload?.llm_task_concurrency ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_task_concurrency
    ),
    llm_model_default_concurrency: Number(
      payload?.llm_model_default_concurrency ?? DEFAULT_LLM_RUNTIME_CONFIG.llm_model_default_concurrency
    ),
    llm_model_concurrency_overrides: normalizeModelConcurrencyOverrides(
      payload?.llm_model_concurrency_overrides
    ),
  }
}

export async function getLlmRuntimeConfig(): Promise<LlmRuntimeConfig> {
  const { data } = await api.get<RawLlmRuntimeConfig>('/api/admin/llm-runtime-config')
  return normalizeLlmRuntimeConfig(data)
}

export async function updateLlmRuntimeConfig(payload: Partial<LlmRuntimeConfig>): Promise<LlmRuntimeConfig> {
  const { data } = await api.put<RawLlmRuntimeConfig>('/api/admin/llm-runtime-config', payload)
  return normalizeLlmRuntimeConfig(data)
}

export async function getAdminUsageRecords(
  page = 1,
  pageSize = 20,
  filters?: {
    search?: string
    model?: string
    user_id?: string
    project_id?: string
  },
): Promise<UsageRecordListResponse> {
  const { data } = await api.get<UsageRecordListResponse>('/api/admin/usage-records', {
    params: {
      page,
      page_size: pageSize,
      ...(filters?.search ? { search: filters.search } : {}),
      ...(filters?.model ? { model: filters.model } : {}),
      ...(filters?.user_id ? { user_id: filters.user_id } : {}),
      ...(filters?.project_id ? { project_id: filters.project_id } : {}),
    },
  })
  return data
}

export async function getUsageRetentionConfig(): Promise<UsageRetentionConfig> {
  const { data } = await api.get<UsageRetentionConfig>('/api/admin/usage-retention-config')
  return {
    retention_days: data.retention_days ?? null,
    max_records: data.max_records ?? null,
  }
}

export async function updateUsageRetentionConfig(
  payload: Partial<UsageRetentionConfig>,
): Promise<UsageRetentionConfig> {
  const { data } = await api.put<UsageRetentionConfig>('/api/admin/usage-retention-config', payload)
  return {
    retention_days: data.retention_days ?? null,
    max_records: data.max_records ?? null,
  }
}

export async function runUsageRetentionCleanup(): Promise<{
  deleted_by_age: number
  deleted_by_count: number
}> {
  const { data } = await api.post<{ deleted_by_age: number; deleted_by_count: number }>(
    '/api/admin/usage-records/cleanup',
  )
  return data
}

export async function getAdminOrders(
  page = 1,
  pageSize = 20,
  filters?: {
    search?: string
    status?: string
    type?: string
    user_id?: string
  },
): Promise<PaymentOrderListResponse> {
  const { data } = await api.get<PaymentOrderListResponse>('/api/admin/orders', {
    params: {
      page,
      page_size: pageSize,
      type: filters?.type ?? 'RECHARGE',
      ...(filters?.search ? { search: filters.search } : {}),
      ...(filters?.status ? { status: filters.status } : {}),
      ...(filters?.user_id ? { user_id: filters.user_id } : {}),
    },
  })
  return data
}

