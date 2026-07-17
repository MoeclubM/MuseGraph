export interface OntologyEntityType {
  name: string
  description?: string
  examples?: string[]
}

export interface OntologyEdgeType {
  name: string
  source_type: string
  target_type: string
  description?: string
}

export interface ProjectOntology {
  entity_types: OntologyEntityType[]
  edge_types: OntologyEdgeType[]
  analysis_summary?: string
  _meta?: {
    model?: string | null
    provider?: string | null
    api_called?: boolean
    input_tokens?: number
    output_tokens?: number
  }
}

export interface AsyncTaskInfo {
  task_id: string
  task_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  updated_at: string
  progress: number
  message: string
  result?: Record<string, any> | null
  error?: string | null
  progress_detail?: Record<string, any> | null
  metadata?: Record<string, any> | null
}

export interface AdminTask extends AsyncTaskInfo {}

export interface AdminTaskListResponse {
  tasks: AdminTask[]
  total: number
  limit: number
}

export type ComponentModelConfig = Record<string, string>
export type OperationPromptConfig = Record<string, string>

export interface User {
  id: string
  email: string
  nickname: string | null
  avatar: string | null
  balance: number
  is_admin: boolean
  status: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  created_at: string
}

export interface UsageRecordItem {
  id: string
  user_id: string
  user_email?: string | null
  user_nickname?: string | null
  project_id?: string | null
  project_title?: string | null
  operation_id?: string | null
  model?: string | null
  provider?: string | null
  input_tokens: number
  output_tokens: number
  cost: number
  billing_mode?: string | null
  request_id?: string | null
  status: string
  source: string
  metadata?: Record<string, unknown> | null
  created_at?: string | null
}

export interface UsageRecordListResponse {
  records: UsageRecordItem[]
  total: number
  page: number
  page_size: number
}

export interface UsageRetentionConfig {
  retention_days: number | null
  max_records: number | null
}

export interface UserUsage {
  total_requests: number
  total_tokens: number
  total_cost: number
  daily_requests: number
  monthly_requests: number
}

export interface AdminUser {
  id: string
  email: string
  nickname: string | null
  is_admin: boolean
  status: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  balance: number
  created_at: string
  usage?: {
    total_requests: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    total_cost: number
  } | null
  recharge?: {
    total_orders: number
    paid_orders: number
    total_amount: number
    paid_amount: number
    last_order_at: string | null
  } | null
  token_usage?: {
    total_tokens: number
    request_count: number
    total_cost: number
  } | null
  recharge_summary?: {
    total_orders: number
    paid_orders: number
    paid_amount: number
  } | null
  // Compatibility for flattened aggregate fields that may still come from the backend
  total_tokens?: number
  total_requests?: number
  total_cost?: number
  total_orders?: number
  paid_orders?: number
  paid_amount?: number
}

export interface ProjectChapter {
  id: string
  project_id: string
  title: string
  content: string
  order_index: number
  created_at: string
  updated_at: string
}

export type ProjectVisibility = 'private' | 'public'

export interface Project {
  id: string
  user_id: string
  title: string
  description: string | null
  visibility?: ProjectVisibility
  current_user_role?: string | null
  current_user_permissions?: string[]
  component_models?: ComponentModelConfig | null
  operation_prompts?: OperationPromptConfig | null
  ontology_schema?: ProjectOntology | null
  creative_state?: ProjectCreativeState | null
  chapters?: ProjectChapter[]
  created_at: string
  updated_at: string
}

export interface PublicProject {
  id: string
  title: string
  description: string | null
  visibility: 'public'
  author_nickname?: string | null
  current_user_role?: string | null
  current_user_permissions?: string[]
  created_at: string
  updated_at: string
}

// ---- Pi Agent workspace types ----

export type AgentSessionStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'partial'
  | string

export interface AgentMessage {
  id?: string
  role: string
  content: string
  created_at?: string
  [key: string]: any
}

export interface AgentStep {
  id?: string
  step_id?: string
  step?: number
  total_steps?: number
  step_type?: string
  title?: string
  message?: string
  tool?: string
  status?: string
  output?: string
  tool_result_preview?: string
  child_session_id?: string
  agent_role?: string
  model?: string
  created_at?: string
  [key: string]: any
}

export interface AgentWorkspaceGraph {
  nodes?: Record<string, any>[]
  edges?: Record<string, any>[]
  [key: string]: any
}

export interface AgentWorkspace {
  structured_memory?: Record<string, any>
  graph?: AgentWorkspaceGraph
  writing_plan?: Record<string, any> | string | null
  last_task?: Record<string, any> | string | null
  [key: string]: any
}

export interface ProjectCreativeState {
  agent_workspace?: AgentWorkspace | null
  [key: string]: any
}

export interface AgentSessionSummary {
  session_id: string
  project_id: string
  role: string
  parent_session_id?: string | null
  root_session_id?: string | null
  parent_step_id?: string | null
  title: string | null
  status: AgentSessionStatus
  message_count: number
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface AgentSessionSnapshot {
  session_id: string
  project_id: string
  role: string
  parent_session_id?: string | null
  root_session_id?: string | null
  parent_step_id?: string | null
  title: string | null
  status: AgentSessionStatus
  model: string
  messages: AgentMessage[]
  steps: AgentStep[]
  children: Record<string, any>[]
  agent_workspace: AgentWorkspace | null
  plan?: Record<string, any> | null
  created_at: string
  updated_at: string
}

export interface AgentChatAccepted {
  session_id: string
  message_id: string
  status: string
  created_at: string
}

export interface AgentSuggestResult {
  suggestions: Record<string, any>[]
  memory_queries: string[]
  raw: string
}
export interface GraphNode {
  id: string
  label: string
  type: string
  [key: string]: any
}

export interface GraphEdge {
  source: string
  target: string
  label: string
  [key: string]: any
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface AuthResponse {
  user: User
  token: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserListResponse {
  users: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface PricingRule {
  id: string
  model: string
  billing_mode: 'TOKEN' | 'REQUEST'
  input_price: number
  output_price: number
  token_unit: number
  request_price: number
  is_active?: boolean
}

export interface StatsResponse {
  total_users: number
  total_projects: number
  total_operations: number
  completed_operations: number
  failed_operations: number
  total_revenue: number
  total_usage_cost: number
  total_balance: number
  average_balance: number
  total_request_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  daily_active_users: number
  last_24h_request_count: number
  last_24h_cost: number
  last_24h_input_tokens: number
  last_24h_output_tokens: number
  last_24h_tokens: number
  last_7d_cost: number
  last_30d_cost: number
  top_users: {
    user_id: string
    email: string
    nickname: string | null
    request_count: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cost: number
  }[]
  top_models: {
    model: string
    request_count: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cost: number
  }[]
  daily_usage: {
    date: string
    request_count: number
    active_users: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cost: number
  }[]
  usage_audit: {
    usage_without_operation: number
    usage_without_project: number
    usage_with_missing_operation_record: number
    usage_with_missing_project_record: number
    usage_with_project_user_mismatch: number
    usage_with_operation_user_mismatch: number
    usage_operation_value_mismatch: number
    negative_balance_users: number
  }
}

export interface Provider {
  id: string
  name: string
  provider: string
  base_url: string | null
  models: string[] | null
  embedding_models?: string[] | null
  reranker_models?: string[] | null
  is_active: boolean
  priority: number
}

export interface LlmRuntimeConfig {
  llm_request_timeout_seconds: number
  llm_retry_count: number
  llm_retry_interval_seconds: number
  llm_prefer_stream: boolean
  llm_stream_fallback_nonstream: boolean
  llm_fallback_model: string
  llm_openai_api_style: string
  llm_reasoning_effort: string
  llm_task_concurrency: number
  llm_model_default_concurrency: number
  llm_model_concurrency_overrides: Record<string, number>
}

export interface PaymentOrder {
  id?: string
  order_no: string
  user_id?: string
  user_email?: string | null
  user_nickname?: string | null
  type?: string
  amount: number
  status: string
  payment_method: string | null
  payment_adapter_id?: string | null
  payment_adapter_name?: string | null
  created_at: string
  paid_at: string | null
}

export interface PaymentOrderListResponse {
  orders: PaymentOrder[]
  total: number
  page: number
  page_size: number
}

export interface EpayAdapterConfig {
  url: string
  pid: string
  key: string
  has_key: boolean
  payment_types: string[]
  notify_url: string
  return_url: string
  enabled_fields_ok?: boolean
}

export interface PaymentAdapterAdmin {
  id: string
  adapter_type: string
  adapter_type_label: string
  display_name: string
  enabled: boolean
  sort_order: number
  valid: boolean
  config: EpayAdapterConfig
  created_at: string | null
  updated_at: string | null
}

export interface PaymentAdapterTypeMeta {
  id: string
  label: string
  description: string
}

export interface PaymentChannelOption {
  id: string
  label: string
}

export interface PublicPaymentAdapter {
  id: string
  type: string
  display_name: string
  sort_order: number
  channels: PaymentChannelOption[]
}

export interface PaymentMethodsResponse {
  adapters: PublicPaymentAdapter[]
}

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastMessage {
  id: number
  message: string
  type: ToastType
}
