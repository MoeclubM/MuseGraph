import api from './index'
import type {
  AgentRun,
  AgentRunEvent,
  AgentRunMode,
  ChangeSet,
} from '@/types'

const agentBase = (projectId: string) => `/api/projects/${projectId}/agent/runs`

export interface StartAgentRunPayload {
  instruction: string
  mode: AgentRunMode
  target_refs?: string[]
  model?: string | null
  effort?: string | null
  skill_slug?: string | null
}

export async function startAgentRun(
  projectId: string,
  payload: StartAgentRunPayload,
): Promise<AgentRun> {
  const { data } = await api.post<AgentRun>(agentBase(projectId), payload)
  return data
}

export async function listAgentRuns(projectId: string): Promise<AgentRun[]> {
  const { data } = await api.get<AgentRun[]>(agentBase(projectId))
  return data
}

export async function getAgentRun(projectId: string, runId: string): Promise<AgentRun> {
  const { data } = await api.get<AgentRun>(`${agentBase(projectId)}/${runId}`)
  return data
}

export async function getAgentRunChanges(projectId: string, runId: string): Promise<ChangeSet> {
  const { data } = await api.get<ChangeSet>(`${agentBase(projectId)}/${runId}/changes`)
  return data
}

export async function cancelAgentRun(projectId: string, runId: string): Promise<AgentRun> {
  const { data } = await api.post<AgentRun>(`${agentBase(projectId)}/${runId}/cancel`)
  return data
}

export async function reviewAgentRun(
  projectId: string,
  runId: string,
  decision: 'accept' | 'reject',
): Promise<AgentRun> {
  const { data } = await api.post<AgentRun>(
    `${agentBase(projectId)}/${runId}/review`,
    { decision },
  )
  return data
}

export interface AgentEventHandlers {
  onEvent: (event: AgentRunEvent) => void
  onClose: (error?: unknown) => void
}

export function streamAgentRun(
  projectId: string,
  runId: string,
  lastEventId: number,
  handlers: AgentEventHandlers,
): () => void {
  const controller = new AbortController()
  const base = import.meta.env.VITE_API_URL || ''
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (lastEventId > 0) headers['Last-Event-ID'] = String(lastEventId)

  void (async () => {
    try {
      const response = await fetch(`${base}${agentBase(projectId)}/${runId}/events`, {
        headers,
        credentials: 'include',
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        throw new Error(`Agent event stream failed with status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let id = 0
      let event = 'message'
      let data: string[] = []
      const dispatch = () => {
        if (!data.length) return
        const parsed = JSON.parse(data.join('\n')) as Record<string, unknown>
        handlers.onEvent({ id, event, data: parsed })
        id = 0
        event = 'message'
        data = []
      }
      const consume = (line: string) => {
        if (!line) return dispatch()
        if (line.startsWith(':')) return
        if (line.startsWith('id:')) id = Number(line.slice(3).trim())
        else if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }

      while (true) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true })
        let newline = buffer.indexOf('\n')
        while (newline >= 0) {
          consume(buffer.slice(0, newline).replace(/\r$/, ''))
          buffer = buffer.slice(newline + 1)
          newline = buffer.indexOf('\n')
        }
      }
      dispatch()
      handlers.onClose()
    } catch (error) {
      handlers.onClose((error as Error).name === 'AbortError' ? undefined : error)
    }
  })()

  return () => controller.abort()
}
