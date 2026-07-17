import api from './index'

export interface ProjectFile {
  path: string
  name: string
  size: number
  content_type: string
  modified_at: string
  text_extractable: boolean
}

export interface ProjectFileContent extends ProjectFile {
  content: string
}

export async function listProjectFiles(projectId: string): Promise<ProjectFile[]> {
  const { data } = await api.get<{ files: ProjectFile[] }>(`/api/projects/${projectId}/files`)
  return data.files
}

export async function readProjectFile(projectId: string, path: string): Promise<ProjectFileContent> {
  const { data } = await api.get<ProjectFileContent>(`/api/projects/${projectId}/files/content`, {
    params: { path },
  })
  return data
}

export async function createProjectFile(
  projectId: string,
  path: string,
  content = '',
): Promise<ProjectFile> {
  const { data } = await api.post<ProjectFile>(`/api/projects/${projectId}/files/manual`, {
    path,
    content,
  })
  return data
}

export async function updateProjectFile(
  projectId: string,
  path: string,
  content: string,
): Promise<ProjectFile> {
  const { data } = await api.put<ProjectFile>(`/api/projects/${projectId}/files/content`, {
    path,
    content,
  })
  return data
}

export async function uploadProjectFile(projectId: string, file: File): Promise<ProjectFile> {
  const body = new FormData()
  body.append('file', file)
  const { data } = await api.post<ProjectFile>(`/api/projects/${projectId}/files`, body, {
    headers: { 'Content-Type': undefined },
  })
  return data
}

export async function deleteProjectFile(projectId: string, path: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}/files`, { params: { path } })
}

export async function renameProjectFile(
  projectId: string,
  path: string,
  newPath: string
): Promise<ProjectFile> {
  const { data } = await api.patch<ProjectFile>(`/api/projects/${projectId}/files/rename`, {
    path,
    new_path: newPath,
  })
  return data
}
