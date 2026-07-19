import api from './index'

export async function downloadProjectBundle(projectId: string): Promise<Blob> {
  const { data } = await api.post<Blob>(
    `/api/projects/${projectId}/export/bundle`,
    {},
    { responseType: 'blob' },
  )
  return data
}

export async function downloadProjectRepository(projectId: string): Promise<Blob> {
  const { data } = await api.post<Blob>(
    `/api/projects/${projectId}/export/repository`,
    {},
    { responseType: 'blob' },
  )
  return data
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
