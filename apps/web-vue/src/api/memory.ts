import api from './index'
import type { AgentRun, GraphData, KnowledgeOperation, KnowledgeRecord } from '@/types'

export interface KnowledgeSnapshot {
  revision_id: string
  dataset_name: string
  records: KnowledgeRecord[]
}

export async function listKnowledge(projectId: string): Promise<KnowledgeSnapshot> {
  const { data } = await api.get<KnowledgeSnapshot>(`/api/projects/${projectId}/memory`)
  return data
}

export async function searchProjectMemory(
  projectId: string,
  query: string,
  topK = 10,
): Promise<{ revision_id: string; results: Record<string, unknown>[] }> {
  const { data } = await api.post<{ revision_id: string; results: Record<string, unknown>[] }>(
    `/api/projects/${projectId}/memory/search`,
    { query, top_k: topK },
  )
  return data
}

export async function proposeKnowledgeChanges(
  projectId: string,
  instruction: string,
  operations: KnowledgeOperation[],
): Promise<AgentRun> {
  const { data } = await api.post<AgentRun>(`/api/projects/${projectId}/memory/changes`, {
    instruction,
    operations,
  })
  return data
}

export async function getMemoryVisualization(projectId: string): Promise<GraphData> {
  const { data } = await api.get<GraphData>(`/api/projects/${projectId}/memory/visualization`)
  return { nodes: data.nodes || [], edges: data.edges || [] }
}
