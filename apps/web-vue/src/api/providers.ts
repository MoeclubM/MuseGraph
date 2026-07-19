import api from './index'
import type { UserProvider } from '@/types'

export interface UserProviderPayload {
  name: string
  provider: string
  api_key?: string
  base_url: string | null
  models: string[]
  embedding_models: string[]
  reranker_models: string[]
  is_active: boolean
  priority: number
}

export async function getMyProviders(): Promise<UserProvider[]> {
  return (await api.get<UserProvider[]>('/api/users/me/providers')).data
}

export async function createMyProvider(
  payload: UserProviderPayload & { api_key: string },
): Promise<UserProvider> {
  return (await api.post<UserProvider>('/api/users/me/providers', payload)).data
}

export async function updateMyProvider(
  id: string,
  payload: UserProviderPayload,
): Promise<UserProvider> {
  return (await api.patch<UserProvider>(`/api/users/me/providers/${id}`, payload)).data
}

export async function deleteMyProvider(id: string): Promise<void> {
  await api.delete(`/api/users/me/providers/${id}`)
}
