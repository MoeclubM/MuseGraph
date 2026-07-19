import api from './index'
import type { ProjectAgent, PromptPhase, PromptTemplate } from '@/types'

export async function listPromptTemplates(): Promise<PromptTemplate[]> {
  return (await api.get<PromptTemplate[]>('/api/users/me/prompt-templates')).data
}

export async function createPromptTemplate(payload: {
  name: string
  description: string
  phase: PromptPhase
  content: string
}): Promise<PromptTemplate> {
  return (await api.post<PromptTemplate>('/api/users/me/prompt-templates', payload)).data
}

export async function updatePromptTemplate(
  id: string,
  payload: Partial<Pick<PromptTemplate, 'name' | 'description' | 'phase' | 'content'>>,
): Promise<PromptTemplate> {
  return (await api.patch<PromptTemplate>(`/api/users/me/prompt-templates/${id}`, payload)).data
}

export async function deletePromptTemplate(id: string): Promise<void> {
  await api.delete(`/api/users/me/prompt-templates/${id}`)
}

export async function listProjectAgents(projectId: string): Promise<ProjectAgent[]> {
  return (await api.get<ProjectAgent[]>(`/api/projects/${projectId}/agents`)).data
}

export async function createProjectAgent(
  projectId: string,
  payload: {
    name: string
    description: string
    model: string | null
    effort: ProjectAgent['effort']
    prompt_template_ids: ProjectAgent['prompt_template_ids']
  },
): Promise<ProjectAgent> {
  return (await api.post<ProjectAgent>(`/api/projects/${projectId}/agents`, payload)).data
}

export async function updateProjectAgent(
  projectId: string,
  id: string,
  payload: Partial<Pick<ProjectAgent, 'name' | 'description' | 'model' | 'effort' | 'prompt_template_ids' | 'enabled'>>,
): Promise<ProjectAgent> {
  return (await api.patch<ProjectAgent>(`/api/projects/${projectId}/agents/${id}`, payload)).data
}

export async function activateProjectAgent(projectId: string, id: string): Promise<ProjectAgent> {
  return (await api.post<ProjectAgent>(`/api/projects/${projectId}/agents/${id}/activate`)).data
}

export async function deleteProjectAgent(projectId: string, id: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/agents/${id}`)
}
