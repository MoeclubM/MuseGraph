import api from './index'
import type { StatsResponse, UserListResponse, OrderListResponse, UserGroup, Provider, ModelPermission } from '@/types'

export async function getStats(): Promise<StatsResponse> {
  const { data } = await api.get<StatsResponse>('/api/admin/stats')
  return data
}

export async function getUsers(page = 1, pageSize = 20): Promise<UserListResponse> {
  const { data } = await api.get<UserListResponse>('/api/admin/users', {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function getGroups(): Promise<UserGroup[]> {
  const { data } = await api.get<UserGroup[]>('/api/admin/groups')
  return data
}

export async function updateUserGroup(userId: string, groupId: string): Promise<void> {
  await api.post(`/api/admin/groups/user/${userId}`, null, { params: { group_id: groupId } })
}

export async function getProviders(): Promise<any[]> {
  const { data } = await api.get('/api/admin/providers')
  return data
}

export async function createProvider(provider: {
  name: string
  provider: string
  api_key: string
  base_url?: string
  models?: string[]
  is_active?: boolean
  priority?: number
}): Promise<any> {
  const { data } = await api.post('/api/admin/providers', provider)
  return data
}

export async function updateProvider(providerId: string, provider: Record<string, any>): Promise<any> {
  const { data } = await api.put(`/api/admin/providers/${providerId}`, provider)
  return data
}

export async function deleteProvider(providerId: string): Promise<void> {
  await api.delete(`/api/admin/providers/${providerId}`)
}

export async function createGroup(group: {
  name: string
  display_name: string
  description?: string
  color?: string
  icon?: string
  allowed_models?: string[]
  quotas?: Record<string, any>
  features?: Record<string, any>
  price?: number
  sort_order?: number
  is_active?: boolean
  is_default?: boolean
}): Promise<any> {
  const { data } = await api.post('/api/admin/groups', group)
  return data
}

export async function updateGroup(groupId: string, group: Record<string, any>): Promise<any> {
  const { data } = await api.put(`/api/admin/groups/${groupId}`, group)
  return data
}

export async function deleteGroup(groupId: string): Promise<void> {
  await api.delete(`/api/admin/groups/${groupId}`)
}

export async function createPricingRule(rule: {
  model: string
  input_price: number
  output_price: number
  is_active?: boolean
}): Promise<any> {
  const { data } = await api.post('/api/admin/pricing', rule)
  return data
}

export async function updatePricingRule(ruleId: string, rule: Record<string, any>): Promise<any> {
  const { data } = await api.put(`/api/admin/pricing/${ruleId}`, rule)
  return data
}

export async function getOrders(page = 1, pageSize = 20): Promise<OrderListResponse> {
  const { data } = await api.get<OrderListResponse>('/api/admin/orders', {
    params: { page, page_size: pageSize },
  })
  return data
}

// --- Plans ---

export async function getPlans(): Promise<any[]> {
  const { data } = await api.get('/api/admin/plans')
  return data
}

export async function createPlan(plan: {
  name: string
  display_name: string
  description?: string
  target_group_id?: string
  price: number
  original_price?: number
  duration: number
  features?: any
  quotas?: Record<string, any>
  allowed_models?: string[]
  is_active?: boolean
  sort_order?: number
}): Promise<any> {
  const { data } = await api.post('/api/admin/plans', plan)
  return data
}

export async function updatePlan(planId: string, plan: Record<string, any>): Promise<any> {
  const { data } = await api.put(`/api/admin/plans/${planId}`, plan)
  return data
}

export async function deletePlan(planId: string): Promise<void> {
  await api.delete(`/api/admin/plans/${planId}`)
}

// --- Pricing Rules ---

export async function getPricingRules(): Promise<any[]> {
  const { data } = await api.get('/api/admin/pricing')
  return data
}

export async function deletePricingRule(ruleId: string): Promise<void> {
  await api.delete(`/api/admin/pricing/${ruleId}`)
}

// --- Model Permissions ---

export async function getModelPermissions(): Promise<any[]> {
  const { data } = await api.get('/api/admin/model-permissions')
  return data
}

export async function createModelPermission(perm: {
  model: string
  group_id: string
  daily_limit?: number
  monthly_limit?: number
  is_active?: boolean
}): Promise<any> {
  const { data } = await api.post('/api/admin/model-permissions', perm)
  return data
}

export async function updateModelPermission(permId: string, perm: Record<string, any>): Promise<any> {
  const { data } = await api.put(`/api/admin/model-permissions/${permId}`, perm)
  return data
}

export async function deleteModelPermission(permId: string): Promise<void> {
  await api.delete(`/api/admin/model-permissions/${permId}`)
}
