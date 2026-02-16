import api from './index'
import type { Project, Operation } from '@/types'

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export async function getModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<{ models: ModelInfo[] }>('/api/ai/models')
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
  content?: string
  simulation_requirement?: string
  component_models?: Record<string, string>
}): Promise<Project> {
  const { data } = await api.post<Project>('/api/projects', payload)
  return data
}

export async function updateProject(
  id: string,
  payload: Partial<Pick<Project, 'title' | 'description' | 'content' | 'simulation_requirement' | 'component_models' | 'oasis_analysis'>>
): Promise<Project> {
  const { data } = await api.put<Project>(`/api/projects/${id}`, payload)
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/projects/${id}`)
}

export async function runOperation(
  projectId: string,
  payload: {
    type: string
    input?: string
    model?: string
    options?: Record<string, any>
  }
): Promise<Operation> {
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation`,
    payload
  )
  return data
}

export async function runOperationStream(
  projectId: string,
  payload: {
    type: string
    input?: string
    model?: string
    options?: Record<string, any>
  }
): Promise<Operation> {
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation/stream`,
    payload
  )
  return data
}

export function getOperationStreamUrl(projectId: string, operationId: string): string {
  const base = import.meta.env.VITE_API_URL || ''
  return `${base}/api/projects/${projectId}/operation/${operationId}/stream`
}

export async function getOperations(projectId: string): Promise<Operation[]> {
  const { data } = await api.get<Operation[]>(`/api/projects/${projectId}/operations`)
  return data
}

export async function runOperationWithFile(
  projectId: string,
  file: File,
  type: string,
  model?: string
): Promise<Operation> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('type', type)
  if (model) formData.append('model', model)
  const { data } = await api.post<Operation>(
    `/api/projects/${projectId}/operation/upload`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return data
}
