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

export interface ContinuationGuidance {
  must_follow: string[]
  next_steps: string[]
  avoid: string[]
}

export interface OasisAgentProfile {
  name: string
  role: string
  persona: string
  stance: string
  likely_actions: string[]
}

export interface OasisTimeConfig {
  total_hours: number
  minutes_per_round: number
  peak_hours: number[]
  off_peak_hours: number[]
}

export interface OasisSimulationEvent {
  title: string
  trigger_hour: number
  description: string
}

export interface OasisAgentActivity {
  name: string
  activity_level: number
  posts_per_hour: number
  response_delay_minutes: number
  stance: string
}

export interface OasisSimulationConfig {
  active_platforms: string[]
  time_config: OasisTimeConfig
  events: OasisSimulationEvent[]
  agent_activity: OasisAgentActivity[]
}

export interface ProjectOasisAnalysis {
  scenario_summary: string
  continuation_guidance?: ContinuationGuidance
  agent_profiles: OasisAgentProfile[]
  simulation_config?: OasisSimulationConfig
  latest_package?: Record<string, any>
  latest_run?: Record<string, any>
  latest_report?: Record<string, any>
}

export interface OasisTask {
  task_id: string
  task_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  updated_at: string
  progress: number
  message: string
  result?: Record<string, any> | null
  error?: string | null
  metadata?: Record<string, any> | null
}

export interface AdminTask extends OasisTask {}

export interface AdminTaskListResponse {
  tasks: AdminTask[]
  total: number
  limit: number
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
  // 兼容后端可能返回的扁平化聚合字段
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

export interface ProjectCharacter {
  id: string
  project_id: string
  name: string
  role: string | null
  profile: string | null
  notes: string | null
  order_index: number
  created_at: string
  updated_at: string
}

export interface ProjectGlossaryTerm {
  id: string
  project_id: string
  term: string
  definition: string
  aliases: string[] | null
  notes: string | null
  order_index: number
  created_at: string
  updated_at: string
}

export interface ProjectWorldbookEntry {
  id: string
  project_id: string
  title: string
  category: string | null
  content: string
  tags: string[] | null
  notes: string | null
  order_index: number
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  user_id: string
  title: string
  description: string | null
  simulation_requirement?: string | null
  component_models?: ComponentModelConfig | null
  ontology_schema?: ProjectOntology | null
  oasis_analysis?: ProjectOasisAnalysis | null
  cognee_dataset_id: string | null
  chapters?: ProjectChapter[]
  created_at: string
  updated_at: string
}

export interface Operation {
  id: string
  project_id: string
  type: 'CREATE' | 'CONTINUE' | 'ANALYZE' | 'REWRITE' | 'SUMMARIZE'
  input: string | null
  output: string | null
  model: string | null
  input_tokens: number
  output_tokens: number
  cost: number
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED'
  error: string | null
  progress: number
  message: string | null
  metadata: Record<string, any> | null
  created_at: string
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

export interface GraphStatus {
  dataset_id?: string | null
  status: string
  ontology_status?: string | null
  oasis_status?: string | null
  graph_freshness?: 'no_ontology' | 'empty' | 'syncing' | 'stale' | 'fresh' | null
  graph_reason?: string | null
  graph_changed_count?: number | null
  graph_added_count?: number | null
  graph_modified_count?: number | null
  graph_removed_count?: number | null
  graph_last_build_at?: string | null
  graph_mode?: string | null
  graph_syncing_task_id?: string | null
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
  is_active: boolean
  priority: number
}

export interface OasisConfig {
  analysis_prompt_prefix: string
  simulation_prompt_prefix: string
  report_prompt_prefix: string
  max_agent_profiles: number
  max_events: number
  max_agent_activity: number
  min_total_hours: number
  max_total_hours: number
  min_minutes_per_round: number
  max_minutes_per_round: number
  max_posts_per_hour: number
  max_response_delay_minutes: number
  allowed_platforms: string[]
  llm_request_timeout_seconds: number
  llm_retry_count: number
  llm_retry_interval_seconds: number
  llm_prefer_stream: boolean
  llm_stream_fallback_nonstream: boolean
  llm_task_concurrency: number
  llm_model_default_concurrency: number
  llm_model_concurrency_overrides: Record<string, number>
}

export interface PaymentOrder {
  id?: string
  order_no: string
  user_id?: string
  type?: string
  amount: number
  status: string
  payment_method: string | null
  created_at: string
  paid_at: string | null
}

export interface PaymentOrderListResponse {
  orders: PaymentOrder[]
  total: number
  page: number
  page_size: number
}

export interface PaymentConfig {
  enabled: boolean
  url: string
  pid: string
  key: string
  has_key: boolean
  payment_type: string
  notify_url: string
  return_url: string
}

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastMessage {
  id: number
  message: string
  type: ToastType
}

export interface SimulationRuntime {
  simulation_id: string
  project_id: string
  status: string
  simulation_config: Record<string, any>
  profiles: Record<string, any>[]
  run_state: Record<string, any>
  env_status: Record<string, any>
  metadata?: {
    source_chapter_ids?: string[]
    content_hash?: string
    generated_at?: string
    [key: string]: any
  }
  created_at?: string | null
  updated_at?: string | null
}

export interface ReportRuntime {
  report_id: string
  simulation_id: string
  status: string
  title: string
  executive_summary: string
  markdown: string
  key_findings?: string[]
  next_actions?: string[]
  generated_at?: string | null
}

// Simulation UI Types
export interface LogEntry {
  id: string
  timestamp: string
  level: 'info' | 'warning' | 'error' | 'success'
  message: string
  source?: string
}

export interface SimulationAction {
  action_id: string
  round_num: number
  agent: string
  action_type: 'post' | 'comment' | 'react' | 'share'
  summary: string
  created_at: string
  platform?: string
}

export type ViewMode = 'graph' | 'split' | 'workbench'
