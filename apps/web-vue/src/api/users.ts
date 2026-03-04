import api from './index'
import type { UserUsage } from '@/types'

export async function getUserUsage(userId: string): Promise<UserUsage> {
  const { data } = await api.get<UserUsage>(`/api/users/${userId}/usage`)
  return data
}
