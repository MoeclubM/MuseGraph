import api from './index'
import type { SimulationAction, SimulationRuntime } from '@/types'

type RawTimelineEntry = Record<string, any>

function normalizeActionKind(rawType: string): SimulationAction['action_kind'] {
  const value = rawType.toLowerCase()

  if (/comment|reply|response|respond/.test(value)) return 'response'
  if (/react|like|vote|signal|feedback/.test(value)) return 'signal'
  if (/share|forward|repost|boost|amplif/.test(value)) return 'amplification'
  if (/post|create|publish|seed|start|init/.test(value)) return 'seed'

  return 'update'
}

function normalizeActionLabel(kind: SimulationAction['action_kind']): string {
  switch (kind) {
    case 'seed':
      return 'Initial Move'
    case 'response':
      return 'Follow-up'
    case 'signal':
      return 'Signal Update'
    case 'amplification':
      return 'Spread'
    default:
      return 'State Update'
  }
}

function normalizeSimulationAction(entry: RawTimelineEntry): SimulationAction {
  const rawActionType = String(entry.action_type || entry.type || entry.action || '').trim()
  const actionKind = normalizeActionKind(rawActionType)

  return {
    action_id: String(entry.action_id || entry.id || `${entry.round_num || 0}-${entry.created_at || entry.timestamp || Date.now()}`),
    round_num: Number(entry.round_num || entry.round || 0),
    agent: String(entry.agent || entry.agent_name || entry.actor || entry.name || 'Unknown Actor'),
    action_kind: actionKind,
    action_label: normalizeActionLabel(actionKind),
    summary: String(entry.summary || entry.result || entry.content || entry.description || ''),
    created_at: String(entry.created_at || entry.timestamp || new Date().toISOString()),
  }
}

export async function createSimulation(payload: {
  project_id: string
  graph_id?: string
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

export async function getSimulationTimelineEntries(
  simulationId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<SimulationAction[]> {
  const { data } = await api.get<{ status: string; data: RawTimelineEntry[] }>(
    `/api/simulation/${simulationId}/actions`,
    { params }
  )
  return Array.isArray(data.data) ? data.data.map(normalizeSimulationAction) : []
}

