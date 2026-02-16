import api from './index'
import type { GraphData, OasisTask, ProjectOntology, ProjectOasisAnalysis } from '@/types'

export async function addToGraph(
  projectId: string,
  text: string,
  ontology?: ProjectOntology | null
): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>(
    `/api/projects/${projectId}/graphs`,
    { text, ontology: ontology || undefined }
  )
  return data
}

export async function generateOntology(
  projectId: string,
  text: string,
  requirement?: string,
  model?: string
): Promise<{ status: string; ontology: ProjectOntology }> {
  const { data } = await api.post<{ status: string; ontology: ProjectOntology }>(
    `/api/projects/${projectId}/graphs/ontology/generate`,
    { text, requirement, model }
  )
  return data
}

export async function analyzeWithOasis(
  projectId: string,
  payload: {
    text?: string
    requirement?: string
    prompt?: string
    model?: string
    analysis_model?: string
    simulation_model?: string
  }
): Promise<{ status: string; analysis: ProjectOasisAnalysis; context: Record<string, any> }> {
  const { data } = await api.post<{ status: string; analysis: ProjectOasisAnalysis; context: Record<string, any> }>(
    `/api/projects/${projectId}/graphs/oasis/analyze`,
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
    model?: string
    analysis_model?: string
    simulation_model?: string
  } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${projectId}/graphs/oasis/prepare/task`,
    payload
  )
  return data
}

export async function startRunOasisTask(
  projectId: string,
  payload: { package?: Record<string, any> } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${projectId}/graphs/oasis/run/task`,
    payload
  )
  return data
}

export async function startReportOasisTask(
  projectId: string,
  payload: { model?: string; report_model?: string } = {}
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.post<{ status: string; task: OasisTask }>(
    `/api/projects/${projectId}/graphs/oasis/report/task`,
    payload
  )
  return data
}

export async function getOasisTaskStatus(
  projectId: string,
  taskId: string
): Promise<{ status: string; task: OasisTask }> {
  const { data } = await api.get<{ status: string; task: OasisTask }>(
    `/api/projects/${projectId}/graphs/oasis/tasks/${taskId}`
  )
  return data
}

export async function getGraphStatus(projectId: string): Promise<{
  dataset_id: string | null
  status: string
  ontology_status?: string | null
  oasis_status?: string | null
}> {
  const { data } = await api.get<{
    dataset_id: string | null
    status: string
    ontology_status?: string | null
    oasis_status?: string | null
  }>(
    `/api/projects/${projectId}/graphs`
  )
  return data
}

export async function searchGraph(
  projectId: string,
  query: string,
  searchType?: string,
  topK?: number
): Promise<any[]> {
  const payload: Record<string, any> = { query }
  if (searchType) payload.search_type = searchType
  if (topK) payload.top_k = topK
  const { data } = await api.post<{ results: any[] }>(
    `/api/projects/${projectId}/graphs/search`,
    payload
  )
  return data.results
}

export async function getVisualization(projectId: string): Promise<GraphData> {
  const { data } = await api.get<GraphData>(
    `/api/projects/${projectId}/graphs/visualization`
  )
  return data
}

export async function deleteGraph(projectId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/graphs`)
}
