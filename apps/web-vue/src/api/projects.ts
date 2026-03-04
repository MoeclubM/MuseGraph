import api from './index'
import type { Project, Operation, ProjectChapter } from '@/types'

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export interface RunOperationPayload {
  type: string
  input?: string
  model?: string
  chapter_ids?: string[]
  use_rag?: boolean
}

export async function getModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/models')
  return data.models
}

export async function getEmbeddingModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/embedding-models')
  return data.models
}

export async function getProjects(): Promise<Project[]> {
  const { data } = await api.get<Project[]>('/api/projects')
  return data
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/api/projects/${id}`)
  return data
}

export async function createProject(payload: {
  title: string
  description?: string
  simulation_requirement?: string
  component_models?: Record<string, string>
}): Promise<Project> {
  const { data } = await api.post<Project>('/api/projects', payload)
  return data
}

export async function updateProject(
  id: string,
  payload: Partial<Pick<Project, 'title' | 'description' | 'simulation_requirement' | 'component_models' | 'oasis_analysis'>>
): Promise<Project> {
  const { data } = await api.put<Project>(`/api/projects/${id}`, payload)
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/projects/${id}`)
}

export async function runOperation(
  projectId: string,
  payload: RunOperationPayload
): Promise<Operation> {
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation`,
    payload
  )
  return data
}

export async function getOperations(projectId: string): Promise<Operation[]> {
  const { data } = await api.get<Operation[]>(`/api/projects/${projectId}/operations`)
  return data
}

export async function listProjectChapters(projectId: string): Promise<ProjectChapter[]> {
  const { data } = await api.get<ProjectChapter[]>(`/api/projects/${projectId}/chapters`)
  return data
}

export async function createProjectChapter(
  projectId: string,
  payload: {
    title?: string
    content?: string
    order_index?: number
  }
): Promise<ProjectChapter> {
  const { data } = await api.post<ProjectChapter>(`/api/projects/${projectId}/chapters`, payload)
  return data
}

export async function updateProjectChapter(
  projectId: string,
  chapterId: string,
  payload: {
    title?: string
    content?: string
    order_index?: number
  }
): Promise<ProjectChapter> {
  const { data } = await api.put<ProjectChapter>(`/api/projects/${projectId}/chapters/${chapterId}`, payload)
  return data
}

export async function deleteProjectChapter(projectId: string, chapterId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/chapters/${chapterId}`)
}

export async function reorderProjectChapters(
  projectId: string,
  chapterIdsInOrder: string[]
): Promise<ProjectChapter[]> {
  const chapters = chapterIdsInOrder.map((id, index) => ({ id, order_index: index }))
  const { data } = await api.post<ProjectChapter[]>(`/api/projects/${projectId}/chapters/reorder`, { chapters })
  return data
}
