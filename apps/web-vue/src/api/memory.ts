import api from './index'
import type { GraphData } from '@/types'

export interface MemoryStatus {
  memory_id?: string | null
  status: string
  ontology_status?: string | null
  text_type?: string | null
  memory_freshness?: string | null
  memory_reason?: string | null
  memory_changed_count?: number | null
  memory_last_build_at?: string | null
  memory_mode?: string | null
  memory_syncing_task_id?: string | null
}

export interface MemoryTaskInfo {
  task_id: string
  task_type: string
  status: string
  created_at: string
  updated_at: string
  progress?: number
  message?: string
  error?: string | null
}

export interface MemoryBuildPayload {
  text?: string
  chapter_ids?: string[]
  build_mode?: 'rebuild' | 'incremental'
}

export async function getMemoryStatus(projectId: string): Promise<MemoryStatus> {
  const { data } = await api.get<MemoryStatus>(`/api/projects/${projectId}/memory`)
  return data
}

export async function startMemoryBuildTask(
  projectId: string,
  payload: MemoryBuildPayload = {},
): Promise<{ status: string; task: MemoryTaskInfo }> {
  const { data } = await api.post<{ status: string; task: MemoryTaskInfo }>(
    `/api/projects/${projectId}/memory/build/task`,
    {
      text: payload.text || '',
      build_mode: payload.build_mode || 'rebuild',
      chapter_ids: payload.chapter_ids,
    },
  )
  return data
}

export async function getMemoryTask(projectId: string, taskId: string): Promise<{ status: string; task: MemoryTaskInfo }> {
  const { data } = await api.get<{ status: string; task: MemoryTaskInfo }>(
    `/api/projects/${projectId}/memory/tasks/${taskId}`,
  )
  return data
}

export async function deleteProjectMemory(projectId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/memory`)
}

export async function searchProjectMemory(
  projectId: string,
  query: string,
  options?: { search_type?: string; top_k?: number },
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(`/api/projects/${projectId}/memory/search`, {
    query,
    search_type: options?.search_type || 'INSIGHTS',
    top_k: options?.top_k || 10,
  })
  return data
}

export async function getMemoryVisualization(
  projectId: string,
  options?: { previewTaskId?: string },
): Promise<GraphData> {
  const params = options?.previewTaskId ? { preview_task_id: options.previewTaskId } : undefined
  const { data } = await api.get<GraphData>(`/api/projects/${projectId}/memory/visualization`, { params })
  return {
    nodes: Array.isArray(data.nodes) ? data.nodes : [],
    edges: Array.isArray(data.edges) ? data.edges : [],
  }
}
