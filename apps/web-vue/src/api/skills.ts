import api from './index'

export interface SkillItem {
  id: string
  slug: string
  name: string
  icon?: string | null
  description: string
  scope: string[]
  tags: string[]
  is_builtin: boolean
  is_active?: boolean
  owner_project_id: string | null
  default_model_component?: string | null
  system_prompt?: string
  allowed_tools?: string[] | null
}

export interface SkillCreatePayload {
  slug: string
  name: string
  description?: string
  system_prompt: string
  icon?: string | null
  scope?: string[]
  tags?: string[]
  allowed_tools?: string[] | null
  default_model_component?: string | null
}

function skillsBase(projectId: string): string {
  return `/api/projects/${projectId}/skills`
}

export async function listSkills(
  projectId: string,
  scope: string = 'chat',
): Promise<SkillItem[]> {
  const { data } = await api.get<SkillItem[]>(skillsBase(projectId), {
    params: { scope },
  })
  return data
}

export async function createSkill(
  projectId: string,
  payload: SkillCreatePayload,
): Promise<SkillItem> {
  const { data } = await api.post<SkillItem>(skillsBase(projectId), payload)
  return data
}

export async function deleteSkill(projectId: string, slug: string): Promise<void> {
  await api.delete(`${skillsBase(projectId)}/${slug}`)
}

export async function toggleSkill(
  projectId: string,
  slug: string,
  enabled: boolean,
): Promise<{ ok: boolean; slug: string; enabled: boolean; is_builtin: boolean }> {
  const { data } = await api.post<{
    ok: boolean
    slug: string
    enabled: boolean
    is_builtin: boolean
  }>(`${skillsBase(projectId)}/${slug}/toggle`, { enabled })
  return data
}
