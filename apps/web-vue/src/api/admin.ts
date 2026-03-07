import api from './index'
import type {
  AdminTask,
  AdminTaskListResponse,
  StatsResponse,
  UserListResponse,
  Provider,
  PricingRule,
  AdminUser,
  PaymentConfig,
  OasisConfig,
  PaymentOrderListResponse,
} from '@/types'

type RawOasisConfig = Partial<OasisConfig>

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
}

type ProviderModelKind = 'chat' | 'embedding'

function providerModelPath(providerId: string, kind: ProviderModelKind): string {
  return kind === 'embedding'
    ? `/api/admin/providers/${providerId}/embedding-models`
    : `/api/admin/providers/${providerId}/models`
}

function normalizeProviderModelList(payload: ProviderModelListPayload, kind: ProviderModelKind): string[] {
  return kind === 'embedding'
    ? (payload.embedding_models ?? payload.models ?? [])
    : (payload.models ?? payload.embedding_models ?? [])
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

export async function getAdminTask(taskId: string): Promise<AdminTask> {
  const { data } = await api.get<{ task: AdminTask }>(`/api/admin/tasks/${taskId}`)
  return data.task
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

export async function addUserBalance(userId: string, amount: number): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>(`/api/admin/users/${userId}/balance`, { amount })
  return data
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

export async function getProviderEmbeddingModels(providerId: string): Promise<string[]> {
  const { data } = await api.get<ProviderModelListPayload>(providerModelPath(providerId, 'embedding'))
  return normalizeProviderModelList(data, 'embedding')
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

export async function deletePricing(ruleId: string): Promise<void> {
  await api.delete(`/api/admin/pricing/${ruleId}`)
}

export async function getPaymentConfig(): Promise<PaymentConfig> {
  const { data } = await api.get<PaymentConfig>('/api/admin/payment-config')
  return data
}

export async function updatePaymentConfig(payload: {
  enabled: boolean
  url: string
  pid: string
  key?: string
  payment_type?: string
  notify_url?: string
  return_url?: string
}): Promise<PaymentConfig> {
  const { data } = await api.put<PaymentConfig>('/api/admin/payment-config', payload)
  return data
}

const DEFAULT_OASIS_CONFIG: OasisConfig = {
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
  llm_task_concurrency: 1,
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

function normalizeOasisConfig(payload: RawOasisConfig | null | undefined): OasisConfig {
  return {
    analysis_prompt_prefix: String(payload?.analysis_prompt_prefix || ''),
    simulation_prompt_prefix: String(payload?.simulation_prompt_prefix || ''),
    report_prompt_prefix: String(payload?.report_prompt_prefix || ''),
    max_agent_profiles: Number(payload?.max_agent_profiles ?? DEFAULT_OASIS_CONFIG.max_agent_profiles),
    max_events: Number(payload?.max_events ?? DEFAULT_OASIS_CONFIG.max_events),
    max_agent_activity: Number(payload?.max_agent_activity ?? DEFAULT_OASIS_CONFIG.max_agent_activity),
    min_total_hours: Number(payload?.min_total_hours ?? DEFAULT_OASIS_CONFIG.min_total_hours),
    max_total_hours: Number(payload?.max_total_hours ?? DEFAULT_OASIS_CONFIG.max_total_hours),
    min_minutes_per_round: Number(payload?.min_minutes_per_round ?? DEFAULT_OASIS_CONFIG.min_minutes_per_round),
    max_minutes_per_round: Number(payload?.max_minutes_per_round ?? DEFAULT_OASIS_CONFIG.max_minutes_per_round),
    max_actions_per_hour: Number(payload?.max_actions_per_hour ?? DEFAULT_OASIS_CONFIG.max_actions_per_hour),
    max_response_delay_minutes: Number(payload?.max_response_delay_minutes ?? DEFAULT_OASIS_CONFIG.max_response_delay_minutes),
    llm_request_timeout_seconds: Number(
      payload?.llm_request_timeout_seconds ?? DEFAULT_OASIS_CONFIG.llm_request_timeout_seconds
    ),
    llm_retry_count: Number(payload?.llm_retry_count ?? DEFAULT_OASIS_CONFIG.llm_retry_count),
    llm_retry_interval_seconds: Number(
      payload?.llm_retry_interval_seconds ?? DEFAULT_OASIS_CONFIG.llm_retry_interval_seconds
    ),
    llm_prefer_stream:
      typeof payload?.llm_prefer_stream === 'boolean'
        ? payload.llm_prefer_stream
        : DEFAULT_OASIS_CONFIG.llm_prefer_stream,
    llm_stream_fallback_nonstream:
      typeof payload?.llm_stream_fallback_nonstream === 'boolean'
        ? payload.llm_stream_fallback_nonstream
        : DEFAULT_OASIS_CONFIG.llm_stream_fallback_nonstream,
    llm_task_concurrency: Number(
      payload?.llm_task_concurrency ?? DEFAULT_OASIS_CONFIG.llm_task_concurrency
    ),
    llm_model_default_concurrency: Number(
      payload?.llm_model_default_concurrency ?? DEFAULT_OASIS_CONFIG.llm_model_default_concurrency
    ),
    llm_model_concurrency_overrides: normalizeModelConcurrencyOverrides(
      payload?.llm_model_concurrency_overrides
    ),
  }
}

export async function getOasisConfig(): Promise<OasisConfig> {
  const { data } = await api.get<RawOasisConfig>('/api/admin/oasis-config')
  return normalizeOasisConfig(data)
}

export async function updateOasisConfig(payload: Partial<OasisConfig>): Promise<OasisConfig> {
  const { data } = await api.put<RawOasisConfig>('/api/admin/oasis-config', payload)
  return normalizeOasisConfig(data)
}

export async function getUserOrders(
  userId: string,
  page = 1,
  pageSize = 20,
): Promise<PaymentOrderListResponse> {
  const { data } = await api.get<PaymentOrderListResponse>(`/api/admin/users/${userId}/orders`, {
    params: { page, page_size: pageSize },
  })
  return data
}

