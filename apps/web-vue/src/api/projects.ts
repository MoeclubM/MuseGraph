import api from './index'
import type { Project, ProjectVisibility, PublicProject } from '@/types'

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  role: 'owner' | 'editor' | 'viewer'
  created_at: string
  updated_at: string
}

export async function getModels(): Promise<ModelInfo[]> {
  return (await api.get<{ models: ModelInfo[] }>('/api/ai/models')).data.models
}

export async function getEmbeddingModels(): Promise<ModelInfo[]> {
  return (await api.get<{ models: ModelInfo[] }>('/api/ai/embedding-models')).data.models
}

export async function getRerankerModels(): Promise<ModelInfo[]> {
  return (await api.get<{ models: ModelInfo[] }>('/api/ai/reranker-models')).data.models
}

export async function getProjects(): Promise<Project[]> {
  return (await api.get<Project[]>('/api/projects')).data
}

export async function getPublicProjects(params?: {
  page?: number
  page_size?: number
  q?: string
}): Promise<PublicProject[]> {
  const limit = params?.page_size || 20
  const offset = ((params?.page || 1) - 1) * limit
  const { data } = await api.get<{ items: PublicProject[]; total: number }>('/api/projects/public', {
    params: { query: params?.q, limit, offset },
  })
  return data.items
}

export async function updateProjectVisibility(
  id: string,
  visibility: ProjectVisibility,
): Promise<Project> {
  return (await api.patch<Project>(`/api/projects/${id}/visibility`, { visibility })).data
}

export async function getProject(id: string): Promise<Project> {
  return (await api.get<Project>(`/api/projects/${id}`)).data
}

export async function createProject(payload: {
  title: string
  description?: string
  visibility?: ProjectVisibility
  pack_slug?: Project['pack_slug']
  component_models?: Record<string, string>
}): Promise<Project> {
  return (await api.post<Project>('/api/projects', payload)).data
}

export async function updateProject(
  id: string,
  payload: Partial<Pick<Project, 'title' | 'description' | 'component_models' | 'pack_slug'>>,
): Promise<Project> {
  return (await api.patch<Project>(`/api/projects/${id}`, payload)).data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/projects/${id}`)
}

export async function listProjectMembers(id: string): Promise<ProjectMember[]> {
  return (await api.get<ProjectMember[]>(`/api/projects/${id}/members`)).data
}

export async function addProjectMember(
  id: string,
  userId: string,
  role: 'editor' | 'viewer',
): Promise<ProjectMember> {
  return (await api.post<ProjectMember>(`/api/projects/${id}/members`, {
    user_id: userId,
    role,
  })).data
}

export async function updateProjectMember(
  id: string,
  memberId: string,
  role: 'editor' | 'viewer',
): Promise<ProjectMember> {
  return (await api.patch<ProjectMember>(`/api/projects/${id}/members/${memberId}`, { role })).data
}

export async function deleteProjectMember(id: string, memberId: string): Promise<void> {
  await api.delete(`/api/projects/${id}/members/${memberId}`)
}
