import api from './index'
import type {
  Project,
  ProjectVisibility,
  PublicProject,
  ProjectChapter,
} from '@/types'

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export async function getModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/models')
  return data.models
}

export async function getEmbeddingModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/embedding-models')
  return data.models
}

export async function getRerankerModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/reranker-models')
  return data.models
}

export async function getProjects(): Promise<Project[]> {
  const { data } = await api.get<Project[]>('/api/projects')
  return data
}

export async function getPublicProjects(params?: {
  page?: number
  page_size?: number
  q?: string
}): Promise<PublicProject[]> {
  const { data } = await api.get<PublicProject[]>('/api/projects/public', { params })
  return data
}

export async function updateProjectVisibility(
  id: string,
  visibility: ProjectVisibility
): Promise<Project> {
  const { data } = await api.put<Project>(`/api/projects/${id}/visibility`, { visibility })
  return data
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/api/projects/${id}`)
  return data
}

export async function createProject(payload: {
  title: string
  description?: string
  component_models?: Record<string, string>
  operation_prompts?: Record<string, string>
}): Promise<Project> {
  const { data } = await api.post<Project>('/api/projects', payload)
  return data
}

export async function updateProject(
  id: string,
  payload: Partial<Pick<Project, 'title' | 'description' | 'component_models' | 'operation_prompts'>>
): Promise<Project> {
  const { data } = await api.put<Project>(`/api/projects/${id}`, payload)
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/projects/${id}`)
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