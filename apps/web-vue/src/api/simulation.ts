import api from './index'
import type { SimulationRuntime } from '@/types'

export async function createSimulation(payload: {
  project_id: string
  graph_id?: string
  enable_twitter?: boolean
  enable_reddit?: boolean
  chapter_ids?: string[]
}): Promise<{ simulation_id: string; project_id: string; graph_id: string; status: string }> {
  const { data } = await api.post<{ status: string; data: { simulation_id: string; project_id: string; graph_id: string; status: string } }>(
    '/api/simulation/create',
    payload
  )
  return data.data
}

export async function prepareSimulation(payload: {
  simulation_id: string
  force_regenerate?: boolean
  use_llm_for_profiles?: boolean
  parallel_profile_count?: number
  chapter_ids?: string[]
}): Promise<{ simulation_id: string; task_id?: string; already_prepared?: boolean; message?: string }> {
  const { data } = await api.post<{ status: string; data: { simulation_id: string; task_id?: string; already_prepared?: boolean; message?: string } }>(
    '/api/simulation/prepare',
    payload
  )
  return data.data
}

export async function getSimulation(simulationId: string): Promise<SimulationRuntime> {
  const { data } = await api.get<{ status: string; data: SimulationRuntime }>(`/api/simulation/${simulationId}`)
  return data.data
}

export async function listSimulations(projectId?: string): Promise<SimulationRuntime[]> {
  const { data } = await api.get<{ status: string; data: SimulationRuntime[] }>('/api/simulation/list', {
    params: projectId ? { project_id: projectId } : undefined,
  })
  return data.data
}

export async function startSimulation(payload: {
  simulation_id: string
  platform?: string
  max_rounds?: number
  enable_graph_memory_update?: boolean
  force_restart?: boolean
  chapter_ids?: string[]
}): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/simulation/start',
    payload
  )
  return data.data
}

export async function stopSimulation(payload: { simulation_id: string }): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/simulation/stop',
    payload
  )
  return data.data
}

export async function getRunStatus(simulationId: string): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/simulation/${simulationId}/run-status`
  )
  return data.data
}

export async function getRunStatusDetail(simulationId: string): Promise<Record<string, any>> {
  const { data } = await api.get<{ status: string; data: Record<string, any> }>(
    `/api/simulation/${simulationId}/run-status/detail`
  )
  return data.data
}

export async function getSimulationPosts(
  simulationId: string,
  params: { platform?: string; limit?: number; offset?: number } = {}
): Promise<Record<string, any>[]> {
  const { data } = await api.get<{ status: string; data: Record<string, any>[] }>(
    `/api/simulation/${simulationId}/posts`,
    { params }
  )
  return data.data
}

export async function getSimulationComments(
  simulationId: string,
  params: { platform?: string; limit?: number; offset?: number } = {}
): Promise<Record<string, any>[]> {
  const { data } = await api.get<{ status: string; data: Record<string, any>[] }>(
    `/api/simulation/${simulationId}/comments`,
    { params }
  )
  return data.data
}

export async function getSimulationTimeline(
  simulationId: string,
  params: { start_round?: number; end_round?: number } = {}
): Promise<Record<string, any>[]> {
  const { data } = await api.get<{ status: string; data: Record<string, any>[] }>(
    `/api/simulation/${simulationId}/timeline`,
    { params }
  )
  return data.data
}

export async function getSimulationActions(
  simulationId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<Record<string, any>[]> {
  const { data } = await api.get<{ status: string; data: Record<string, any>[] }>(
    `/api/simulation/${simulationId}/actions`,
    { params }
  )
  return data.data
}

export async function getAgentStats(simulationId: string): Promise<Record<string, any>[]> {
  const { data } = await api.get<{ status: string; data: Record<string, any>[] }>(
    `/api/simulation/${simulationId}/agent-stats`
  )
  return data.data
}

export async function interviewAgent(payload: {
  simulation_id: string
  prompt: string
  agent_id?: string | number
}): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/simulation/interview',
    payload
  )
  return data.data
}

export async function interviewAgents(payload: {
  simulation_id: string
  interviews: Array<{ prompt: string; agent_id?: string | number }>
}): Promise<Record<string, any>[]> {
  const { data } = await api.post<{ status: string; data: Record<string, any>[] }>(
    '/api/simulation/interview/batch',
    payload
  )
  return data.data
}

export async function interviewAllAgents(payload: {
  simulation_id: string
  prompt: string
}): Promise<Record<string, any>[]> {
  const { data } = await api.post<{ status: string; data: Record<string, any>[] }>(
    '/api/simulation/interview/all',
    payload
  )
  return data.data
}

export async function getInterviewHistory(payload: {
  simulation_id: string
  limit?: number
  offset?: number
}): Promise<Record<string, any>[]> {
  const { data } = await api.post<{ status: string; data: Record<string, any>[] }>(
    '/api/simulation/interview/history',
    payload
  )
  return data.data
}

export async function getEnvStatus(payload: { simulation_id: string }): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/simulation/env-status',
    payload
  )
  return data.data
}

export async function closeSimulationEnv(payload: { simulation_id: string }): Promise<Record<string, any>> {
  const { data } = await api.post<{ status: string; data: Record<string, any> }>(
    '/api/simulation/close-env',
    payload
  )
  return data.data
}
