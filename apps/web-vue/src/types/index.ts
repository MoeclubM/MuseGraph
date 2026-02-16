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
  key_drivers: string[]
  risk_signals: string[]
  opportunity_signals: string[]
  timeline: string[]
  continuation_guidance: ContinuationGuidance
  agent_profiles: OasisAgentProfile[]
  simulation_config?: OasisSimulationConfig
  evidence?: Record<string, any>
  latest_package?: Record<string, any>
  latest_run?: Record<string, any>
  latest_report?: Record<string, any>
}

export interface OasisTask {
  task_id: string
  task_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  updated_at: string
  progress: number
  message: string
  result?: Record<string, any> | null
  error?: string | null
  metadata?: Record<string, any> | null
}

export type ComponentModelConfig = Record<string, string>

export interface User {
  id: string
  email: string
  username: string
  nickname: string | null
  avatar: string | null
  balance: number
  role: 'USER' | 'ADMIN'
  group_id: string | null
  status: 'ACTIVE' | 'SUSPENDED' | 'DELETED'
  created_at: string
}

export interface Project {
  id: string
  user_id: string
  title: string
  description: string | null
  content: string | null
  simulation_requirement?: string | null
  component_models?: ComponentModelConfig | null
  ontology_schema?: ProjectOntology | null
  oasis_analysis?: ProjectOasisAnalysis | null
  cognee_dataset_id: string | null
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
  users: Record<string, any>[]
  total: number
  page: number
  page_size: number
}

export interface OrderListResponse {
  orders: Record<string, any>[]
  total: number
  page: number
  page_size: number
}

export interface UserGroup {
  id: string
  name: string
  display_name: string
  description: string | null
  color: string | null
  icon: string | null
  price: number | null
  features: Record<string, any> | null
  quotas: Record<string, any> | null
  allowed_models: string[] | null
  is_active: boolean
  is_default: boolean
  sort_order: number
}

export interface PricingRule {
  id: string
  model: string
  input_price: number
  output_price: number
}

export interface Plan {
  id: string
  name: string
  display_name: string
  description: string | null
  price: number
  original_price: number | null
  duration: number
  features: string[] | Record<string, any> | null
  quotas: Record<string, any> | null
  allowed_models: string[] | null
  is_active: boolean
  sort_order: number
}

export interface StatsResponse {
  total_users: number
  total_projects: number
  total_operations: number
  total_revenue: number
  daily_active_users: number
}

export interface Order {
  id: string
  order_no: string
  user_id: string
  type: string
  amount: number
  status: 'PENDING' | 'PAID' | 'CANCELLED' | 'REFUNDED' | 'EXPIRED'
  payment_method: string | null
  payment_id: string | null
  paid_at: string | null
  created_at: string
}

export interface Provider {
  id: string
  name: string
  provider: string
  base_url: string | null
  models: string[] | null
  is_active: boolean
  priority: number
}

export interface ModelPermission {
  id: string
  model: string
  group_id: string
  daily_limit: number
  monthly_limit: number
  is_active: boolean
}

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastMessage {
  id: number
  message: string
  type: ToastType
}
