export interface AsyncTaskInfo {
  task_id: string
  task_type: string
  status: AgentRunStatus
  created_at: string
  updated_at: string
  message: string
  error?: string | null
  heartbeat_at?: string | null
  lease_owner?: string | null
  cancel_requested: boolean
  metadata?: Record<string, any> | null
}

export interface AdminTask extends AsyncTaskInfo {}

export interface AdminTaskListResponse {
  tasks: AdminTask[]
  total: number
  limit: number
}

export interface AuditLogEntry {
  id: string
  actor_user_id: string | null
  project_id: string | null
  action: string
  target_type: string
  target_id: string | null
  request_id: string | null
  ip_address: string | null
  detail: Record<string, unknown>
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
  limit: number
}

export interface RuntimeHealth {
  status: 'ok' | 'degraded'
  database: 'ok'
  redis: 'ok'
  memory: {
    status: string
    instances: number
  }
  run_counts: Record<string, number>
  stale_worker_leases: number
}

export type ComponentModelConfig = Record<string, string>

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
  active_revision_id?: string | null
  active_agent_id?: string | null
  memory_instance_id?: string | null
  pack_slug: string
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
}

export type AgentRunMode = 'write' | 'analyze' | 'suggest'
export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'awaiting_review'
  | 'accepting'
  | 'completed'
  | 'rejected'
  | 'conflicted'
  | 'failed'
  | 'cancelled'

export interface SourceRef {
  kind: 'file' | 'knowledge' | 'user' | 'external'
  ref: string
  revision?: string | null
  excerpt?: string | null
}

export interface KnowledgeRecord {
  id: string
  kind: 'fact' | 'entity' | 'relation' | 'event' | 'constraint' | 'source'
  title: string
  content: string
  attributes: Record<string, unknown>
  source_refs: SourceRef[]
  revision?: string | null
  entity_type?: string
  source_id?: string
  target_id?: string
  predicate?: string
  occurred_at?: string | null
  severity?: 'required' | 'preferred'
  locator?: string
}

export interface FileChange {
  path: string
  change_type: 'added' | 'modified' | 'deleted'
  before_hash?: string | null
  after_hash?: string | null
  diff: string
}

export interface KnowledgeOperation {
  operation: 'upsert' | 'delete'
  record?: KnowledgeRecord
  record_id?: string
}

export interface ChangeSet {
  files: FileChange[]
  knowledge: KnowledgeOperation[]
  validation?: {
    passed: boolean
    checks: Record<string, unknown>[]
  } | null
  self_review?: {
    passed: boolean
    summary: string
    issues: Record<string, unknown>[]
  } | null
}

export interface AgentRun {
  id: string
  project_id: string
  user_id: string
  base_revision_id: string | null
  result_revision_id: string | null
  agent_id: string
  mode: AgentRunMode
  status: AgentRunStatus
  instruction: string
  model: string | null
  effort: string | null
  target_refs: string[]
  creative_plan: Record<string, unknown> | null
  plan: Record<string, unknown> | null
  context_snapshot: Record<string, unknown> | null
  skill_snapshot: Record<string, unknown>
  agent_snapshot: Record<string, unknown>
  final_output: {
    summary: string
    changed_files: string[]
    knowledge_operations: number
    used_knowledge_ids: string[]
    used_plan_unit_ids: string[]
    unresolved_issues: string[]
  } | null
  error: string | null
  cancel_requested: boolean
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
}

export type PromptPhase = 'architect' | 'planner' | 'writer' | 'auditor' | 'reviser'

export interface PromptTemplate {
  id: string
  user_id: string
  name: string
  description: string
  phase: PromptPhase
  content: string
  version: number
  created_at: string
  updated_at: string
}

export interface ProjectAgent {
  id: string
  project_id: string
  created_by_user_id: string
  name: string
  description: string
  model: string | null
  effort: 'low' | 'medium' | 'high' | null
  prompt_template_ids: Partial<Record<PromptPhase, string>>
  version: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentRunEvent {
  id: number
  event: string
  data: Record<string, unknown>
}

export interface ResolvedSkill {
  slug: string
  name: string
  description: string
  instructions: string
  scopes: AgentRunMode[]
  roles: string[]
  allowed_tools: string[]
  params_schema: Record<string, unknown>
  default_model_component: string | null
  version: number
  source: 'builtin' | 'project'
}

export interface ProjectRevision {
  id: string
  project_id: string
  parent_revision_id: string | null
  git_commit: string
  knowledge_dataset: string
  created_by_run_id: string | null
  status: 'active' | 'superseded'
  message: string
  created_at: string
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
