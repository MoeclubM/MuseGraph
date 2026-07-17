import api from './index'
import type { AgentRun, ProjectRevision } from '@/types'

export async function getProjectVersions(projectId: string): Promise<ProjectRevision[]> {
  const { data } = await api.get<ProjectRevision[]>(`/api/projects/${projectId}/versions`)
  return data
}

export async function restoreProjectVersion(
  projectId: string,
  revisionId: string,
): Promise<AgentRun> {
  const { data } = await api.post<AgentRun>(`/api/projects/${projectId}/versions/restore`, {
    revision_id: revisionId,
  })
  return data
}
