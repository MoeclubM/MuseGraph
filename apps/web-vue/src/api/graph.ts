import api from './index'
import type { GraphData, GraphStatus, OasisTask, ProjectOntology } from '@/types'

export interface GraphSearchOptions {
  searchType?: string
  topK?: number
  useReranker?: boolean
  rerankerTopN?: number
}

function assertProjectId(projectId: string): string {
  const value = String(projectId || '').trim()
  if (!value || value === 'undefined' || value === 'null') {
    throw new Error('Project id is missing')
  }
  return value
}

export async function startGenerateOntologyTask(
  projectId: string,
  payload: {
    text?: string
    requirement?: string
    model?: string
    chapter_ids?: string[]
  }
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/ontology/generate/task`,
    payload
  )
  return data
}

export async function startBuildGraphTask(
  projectId: string,
  payload: {
    text?: string
    ontology?: ProjectOntology | null
    chapter_ids?: string[]
    build_mode?: 'rebuild' | 'incremental'
    resume_failed?: boolean
  }
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/build/task`,
    payload
  )
  return data
}

export async function startAutoSyncGraphTask(
  projectId: string
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/build/auto-sync/task`
  )
  return data
}

export async function startAnalyzeOasisTask(
  projectId: string,
  payload: {
    text?: string
    requirement?: string
    prompt?: string
    analysis_model?: string
    simulation_model?: string
    chapter_ids?: string[]
  } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/oasis/analyze/task`,
    payload
  )
  return data
}

export async function startPrepareOasisTask(
  projectId: string,
  payload: {
    text?: string
    requirement?: string
    prompt?: string
    analysis_model?: string
    simulation_model?: string
    chapter_ids?: string[]
  } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/oasis/prepare/task`,
    payload
  )
  return data
}

export async function startRunOasisTask(
  projectId: string,
  payload: { package?: Record<string, any>; chapter_ids?: string[] } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/oasis/run/task`,
    payload
  )
  return data
}

export async function startReportOasisTask(
  projectId: string,
  payload: { report_model?: string; chapter_ids?: string[] } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/oasis/report/task`,
    payload
  )
  return data
}

export async function getOasisTaskStatus(
  projectId: string,
  taskId: string
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.get<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/tasks/${taskId}`
  )
  return data
}

export async function listGraphTasks(
  projectId: string,
  payload?: { task_type?: string; limit?: number }
): Promise<{ status: string; tasks: OasisTask[] }> {
  const params: Record<string, any> = {}
  if (payload?.task_type) params.task_type = payload.task_type
  if (payload?.limit) params.limit = payload.limit
  const { data } = await api.get<{ status: string; tasks: OasisTask[] }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/tasks`,
    { params }
  )
  return data
}

export async function cancelGraphTask(
  projectId: string,
  taskId: string
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/tasks/${taskId}/cancel`
  )
  return data
}

export async function searchGraph(
  projectId: string,
  query: string,
  options: GraphSearchOptions = {}
): Promise<any[]> {
  const payload: Record<string, any> = { query }
  if (options.searchType) payload.search_type = options.searchType
  if (options.topK) payload.top_k = options.topK
  if (typeof options.useReranker === 'boolean') payload.use_reranker = options.useReranker
  if (options.rerankerTopN) payload.reranker_top_n = options.rerankerTopN
  const { data } = await api.post<{ results: any[] }>(
    `/api/projects/${assertProjectId(projectId)}/graphs/search`,
    payload
  )
  return data.results
}

export async function getVisualization(
  projectId: string,
  options: { previewTaskId?: string } = {}
): Promise<GraphData> {
  const params: Record<string, any> = {}
  if (options.previewTaskId) params.preview_task_id = options.previewTaskId
  const { data } = await api.get<GraphData>(
    `/api/projects/${assertProjectId(projectId)}/graphs/visualization`,
    { params }
  )
  return data
}

export async function getGraphStatus(projectId: string): Promise<GraphStatus> {
  const { data } = await api.get<GraphStatus>(`/api/projects/${assertProjectId(projectId)}/graphs`)
  return data
}
