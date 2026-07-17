import api from './index'

export interface ProjectFact {
  id: string
  project_id: string
  created_by_user_id?: string | null
  created_by_agent_session_id?: string | null
  source_kind: string
  source_ref?: Record<string, unknown> | null
  title: string
  content: string
  metadata?: Record<string, unknown> | null
  ontology_snapshot?: Record<string, unknown> | null
  entities?: Record<string, unknown>[] | null
  relationships?: Record<string, unknown>[] | null
  content_hash: string
  memory_status: string
  memory_task_id?: string | null
  memory_error?: string | null
  created_at: string
  updated_at: string
}

export interface EntityCategory {
  type: string
  label: string
  count: number
  entities: EntityRecord[]
}

export interface EntityRecord {
  id: string
  name: string
  type: string
  summary?: string
  source?: string
  fact_id?: string | null
  attributes?: Record<string, unknown>
}

export interface EntitySearchResponse {
  query: string
  total: number
  results: EntityRecord[]
  categories: EntityCategory[]
}

export interface FactBatchUpdateItem {
  fact_id: string
  title?: string
  content?: string
  entities?: Record<string, unknown>[]
  relationships?: Record<string, unknown>[]
  metadata?: Record<string, unknown>
}

export async function listProjectFacts(projectId: string): Promise<ProjectFact[]> {
  const { data } = await api.get<{ facts: ProjectFact[] }>(`/api/projects/${projectId}/facts`)
  return Array.isArray(data.facts) ? data.facts : []
}

export async function searchProjectEntities(
  projectId: string,
  query: string,
  options?: { entity_type?: string; limit?: number },
): Promise<EntitySearchResponse> {
  const { data } = await api.post<EntitySearchResponse>(`/api/projects/${projectId}/facts/entities/search`, {
    query,
    entity_type: options?.entity_type,
    limit: options?.limit ?? 20,
  })
  return data
}
