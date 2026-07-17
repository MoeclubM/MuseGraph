import api from './index'
import type {
  AgentChatAccepted,
  AgentSessionSnapshot,
  AgentSessionSummary,
} from '@/types'

function agentBase(projectId: string): string {
  return `/api/projects/${projectId}/agent`
}

export interface StartAgentChatPayload {
  message: string
  model?: string
  session_id?: string
  /** Phase A: explicit @-mention or programmatic preset; null/undefined → auto routing. */
  skill_slug?: string | null
  effort?: string | null
}

export async function startAgentChat(
  projectId: string,
  payload: StartAgentChatPayload
): Promise<AgentChatAccepted> {
  const { data } = await api.post<AgentChatAccepted>(`${agentBase(projectId)}/chat`, payload)
  return data
}

export async function getAgentSession(
  projectId: string,
  sessionId: string
): Promise<AgentSessionSnapshot> {
  const { data } = await api.get<AgentSessionSnapshot>(`${agentBase(projectId)}/chat/${sessionId}`)
  return data
}

export async function listAgentSessions(
  projectId: string,
  includeArchived = false
): Promise<AgentSessionSummary[]> {
  const { data } = await api.get<AgentSessionSummary[]>(`${agentBase(projectId)}/sessions`, {
    params: { include_archived: includeArchived },
  })
  return data
}

export async function archiveAgentSession(
  projectId: string,
  sessionId: string
): Promise<AgentSessionSummary> {
  const { data } = await api.post<AgentSessionSummary>(
    `${agentBase(projectId)}/sessions/${sessionId}/archive`
  )
  return data
}

export async function unarchiveAgentSession(
  projectId: string,
  sessionId: string
): Promise<AgentSessionSummary> {
  const { data } = await api.post<AgentSessionSummary>(
    `${agentBase(projectId)}/sessions/${sessionId}/unarchive`
  )
  return data
}

export async function deleteAgentSession(projectId: string, sessionId: string): Promise<void> {
  await api.delete(`${agentBase(projectId)}/sessions/${sessionId}`)
}

export async function cancelAgentSession(projectId: string, sessionId: string): Promise<void> {
  await api.post(`${agentBase(projectId)}/chat/${sessionId}/cancel`)
}

export async function renameAgentSession(
  projectId: string,
  sessionId: string,
  title: string
): Promise<AgentSessionSummary> {
  const { data } = await api.patch<AgentSessionSummary>(
    `${agentBase(projectId)}/sessions/${sessionId}/rename`,
    { title }
  )
  return data
}

export interface AgentStreamHandlers {
  /** 每收到一个完整 SSE 事件回调一次(heartbeat 也会透传) */
  onEvent?: (event: string, data: Record<string, any>) => void
  /** 流结束(服务端关闭/网络错误/主动 abort)时回调;error 为空表示正常关闭 */
  onClose?: (error?: unknown) => void
}

/**
 * 用 fetch + ReadableStream 手动解析 text/event-stream。
 * EventSource 不支持自定义 Authorization header,因此不能使用。
 * 返回 abort 函数,调用后中断连接。
 */
export function streamAgentSession(
  projectId: string,
  sessionId: string,
  handlers: AgentStreamHandlers
): () => void {
  const controller = new AbortController()
  const base = import.meta.env.VITE_API_URL || ''
  const url = `${base}${agentBase(projectId)}/chat/${sessionId}/stream`
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  const token = localStorage.getItem('token')
  if (token) headers.Authorization = `Bearer ${token}`

  void (async () => {
    try {
      const response = await fetch(url, { headers, signal: controller.signal })
      if (!response.ok || !response.body) {
        throw new Error(`SSE request failed with status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventName = ''
      let dataLines: string[] = []

      const dispatch = () => {
        if (dataLines.length === 0) {
          eventName = ''
          return
        }
        const rawData = dataLines.join('\n')
        const name = eventName || 'message'
        eventName = ''
        dataLines = []
        let payload: Record<string, any>
        try {
          const parsed = rawData ? JSON.parse(rawData) : {}
          payload = parsed && typeof parsed === 'object' ? parsed : { value: parsed }
        } catch {
          payload = { raw: rawData }
        }
        handlers.onEvent?.(name, payload)
      }

      const handleLine = (line: string) => {
        if (!line) {
          // 空行 = 一个事件的结束
          dispatch()
          return
        }
        if (line.startsWith(':')) return
        if (line.startsWith('event:')) {
          eventName = line.slice('event:'.length).trim()
          return
        }
        if (line.startsWith('data:')) {
          let value = line.slice('data:'.length)
          if (value.startsWith(' ')) value = value.slice(1)
          dataLines.push(value)
        }
        // 其余字段(id/retry)忽略
      }

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let newlineIndex = buffer.indexOf('\n')
        while (newlineIndex !== -1) {
          let line = buffer.slice(0, newlineIndex)
          buffer = buffer.slice(newlineIndex + 1)
          if (line.endsWith('\r')) line = line.slice(0, -1)
          handleLine(line)
          newlineIndex = buffer.indexOf('\n')
        }
      }
      dispatch()
      handlers.onClose?.()
    } catch (error) {
      if ((error as Error | null)?.name === 'AbortError') {
        handlers.onClose?.()
      } else {
        handlers.onClose?.(error)
      }
    }
  })()

  return () => controller.abort()
}
