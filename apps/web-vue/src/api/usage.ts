import api from './index'
import type { UsageRecordListResponse } from '@/types'

export async function getMyUsageDetails(
  page = 1,
  pageSize = 20,
  filters?: { model?: string; project_id?: string; date_from?: string; date_to?: string },
): Promise<UsageRecordListResponse> {
  const { data } = await api.get<UsageRecordListResponse>('/api/users/me/usage/details', {
    params: {
      page,
      page_size: pageSize,
      ...(filters?.model ? { model: filters.model } : {}),
      ...(filters?.project_id ? { project_id: filters.project_id } : {}),
      ...(filters?.date_from ? { date_from: filters.date_from } : {}),
      ...(filters?.date_to ? { date_to: filters.date_to } : {}),
    },
  })
  return data
}