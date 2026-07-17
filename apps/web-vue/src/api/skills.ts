import api from './index'
import type { AgentRunMode, ResolvedSkill } from '@/types'

export type SkillItem = ResolvedSkill

export interface SkillWritePayload {
  slug: string
  name: string
  description: string
  instructions: string
  scopes: AgentRunMode[]
  roles: string[]
  allowed_tools: string[]
  params_schema: Record<string, unknown>
  default_model_component: string | null
  enabled: boolean
}

const skillsBase = (projectId: string) => `/api/projects/${projectId}/skills`

export async function listSkills(projectId: string): Promise<SkillItem[]> {
  const { data } = await api.get<SkillItem[]>(skillsBase(projectId))
  return data
}

export async function createSkill(
  projectId: string,
  payload: SkillWritePayload,
): Promise<SkillItem> {
  const { data } = await api.post<SkillItem>(skillsBase(projectId), payload)
  return data
}

export async function updateSkill(
  projectId: string,
  slug: string,
  payload: Omit<SkillWritePayload, 'slug'>,
): Promise<SkillItem> {
  const { data } = await api.put<SkillItem>(`${skillsBase(projectId)}/${slug}`, payload)
  return data
}

export async function deleteSkill(projectId: string, slug: string): Promise<void> {
  await api.delete(`${skillsBase(projectId)}/${slug}`)
}

export async function previewSkill(
  projectId: string,
  operation: AgentRunMode,
  role: string,
  slug?: string | null,
): Promise<ResolvedSkill> {
  const { data } = await api.get<ResolvedSkill>(`${skillsBase(projectId)}/resolve/preview`, {
    params: { operation, role, slug: slug || undefined },
  })
  return data
}
