import api from './index'

export interface ProjectRecordPoint {
  id: string
  label: string
  created_at: string
}

export interface ProjectVersionHistory {
  current_record_point: string | null
  record_points: ProjectRecordPoint[]
  pending_changes_count: number
}

export async function getProjectVersionHistory(projectId: string): Promise<ProjectVersionHistory> {
  const { data } = await api.get<ProjectVersionHistory>(`/api/projects/${projectId}/versions`)
  return data
}

export async function createProjectRecordPoint(
  projectId: string,
  message: string
): Promise<ProjectVersionHistory> {
  const { data } = await api.post<ProjectVersionHistory>(
    `/api/projects/${projectId}/versions/record-points`,
    { message }
  )
  return data
}

export async function restoreProjectRecordPoint(
  projectId: string,
  recordPointId: string
): Promise<ProjectVersionHistory> {
  const { data } = await api.post<ProjectVersionHistory>(
    `/api/projects/${projectId}/versions/restore`,
    { record_point_id: recordPointId }
  )
  return data
}
