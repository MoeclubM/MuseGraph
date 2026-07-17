import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AgentSessionSnapshot, AgentSessionSummary, Project } from '@/types'
import * as agentApi from '@/api/agent'
import { getModels, type ModelInfo } from '@/api/projects'

const POLL_INTERVAL_MS = 3000
const AGENT_MODEL_COMPONENT_KEY = 'operation_agent_task'

const RUNNING_STATUSES = new Set(['pending', 'running'])

function isRunningStatus(status: string | undefined | null): boolean {
  return RUNNING_STATUSES.has(String(status || '').toLowerCase())
}

export const useAgentStore = defineStore('agent', () => {
  const sessions = ref<AgentSessionSummary[]>([])
  const sessionsLoading = ref(false)
  const currentSessionId = ref('')
  const currentSession = ref<AgentSessionSnapshot | null>(null)
  const sessionLoading = ref(false)
  const sending = ref(false)
  /** generation_delta 增量 token 缓冲,用于流式气泡 */
  const streamingText = ref('')
  const streamingThinkingText = ref('')
  const models = ref<ModelInfo[]>([])
  const modelsLoading = ref(false)
  const selectedModel = ref('')
  const modelTouched = ref(false)

  // 流和轮询句柄保持非响应式
  let stopStreamFn: (() => void) | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let refreshing = false

  const isSessionRunning = computed(() => isRunningStatus(currentSession.value?.status))

  function stopLiveUpdates() {
    if (stopStreamFn) {
      const stop = stopStreamFn
      stopStreamFn = null
      stop()
    }
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function loadSessions(projectId: string, includeArchived = false) {
    sessionsLoading.value = true
    try {
      sessions.value = await agentApi.listAgentSessions(projectId, includeArchived)
    } finally {
      sessionsLoading.value = false
    }
  }

  function applyDefaultModel(project?: Project | null) {
    if (modelTouched.value && selectedModel.value) return
    const configured = String(
      project?.component_models?.[AGENT_MODEL_COMPONENT_KEY] || ''
    ).trim()
    if (configured) {
      selectedModel.value = configured
      return
    }
    if (selectedModel.value) return
    const ids = models.value.map((m) => m.id)
    selectedModel.value = ids.find((id) => /mimo/i.test(id)) || ids[0] || ''
  }

  async function loadModels(project?: Project | null) {
    modelsLoading.value = true
    try {
      models.value = await getModels()
    } catch {
      models.value = []
    } finally {
      modelsLoading.value = false
    }
    applyDefaultModel(project)
  }

  function setSelectedModel(modelId: string) {
    selectedModel.value = modelId
    modelTouched.value = true
  }

  async function refreshSnapshot(projectId: string) {
    const sessionId = currentSessionId.value
    if (!sessionId || refreshing) return
    refreshing = true
    try {
      const snapshot = await agentApi.getAgentSession(projectId, sessionId)
      if (currentSessionId.value !== sessionId) return
      currentSession.value = snapshot
      if (!isRunningStatus(snapshot.status)) {
        streamingText.value = ''
        streamingThinkingText.value = ''
        stopLiveUpdates()
      }
    } catch {
      // 快照刷新失败不打断 UI;下一次事件/轮询会重试
    } finally {
      refreshing = false
    }
  }

  function startPolling(projectId: string) {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      void refreshSnapshot(projectId)
    }, POLL_INTERVAL_MS)
  }

  function openStream(projectId: string, sessionId: string) {
    stopLiveUpdates()
    stopStreamFn = agentApi.streamAgentSession(projectId, sessionId, {
      onEvent: (event, data) => {
        if (currentSessionId.value !== sessionId) return
        if (event === 'heartbeat') return
        if (event === 'session_snapshot') {
          if (data && data.session_id === sessionId) {
            currentSession.value = data as AgentSessionSnapshot
          }
          return
        }

        if (event === 'thinking_delta') {
          const delta = data?.delta ?? data?.text ?? ''
          if (typeof delta === 'string' && delta) {
            streamingThinkingText.value += delta
          }
          return
        }        if (event === 'generation_delta') {
          const delta = data?.delta ?? data?.text ?? ''
          if (typeof delta === 'string' && delta) {
            streamingText.value += delta
          }
          return
        }
        // 非 delta 事件(progress/step/complete/error 等):重新拉快照最稳妥
        void refreshSnapshot(projectId)
        if (event === 'complete' || event === 'error') {
          streamingText.value = ''
          streamingThinkingText.value = ''
          void loadSessions(projectId).catch(() => {})
        }
      },
      onClose: (error) => {
        stopStreamFn = null
        if (currentSessionId.value !== sessionId) return
        // SSE 断开后若会话仍在运行,降级为 3s 轮询
        if (error || isRunningStatus(currentSession.value?.status)) {
          startPolling(projectId)
        }
      },
    })
  }

  async function selectSession(projectId: string, sessionId: string) {
    stopLiveUpdates()
    currentSessionId.value = sessionId
    streamingText.value = ''
    streamingThinkingText.value = ''
    sessionLoading.value = true
    try {
      const snapshot = await agentApi.getAgentSession(projectId, sessionId)
      if (currentSessionId.value !== sessionId) return
      currentSession.value = snapshot
      if (isRunningStatus(snapshot.status)) {
        openStream(projectId, sessionId)
      }
    } finally {
      sessionLoading.value = false
    }
  }

  function startNewSession() {
    stopLiveUpdates()
    currentSessionId.value = ''
    currentSession.value = null
    streamingText.value = ''
    streamingThinkingText.value = ''
  }

  async function sendMessage(
    projectId: string,
    message: string,
    options: { skill_slug?: string | null; effort?: string | null } = {},
  ) {
    sending.value = true
    try {
      const accepted = await agentApi.startAgentChat(projectId, {
        message,
        model: selectedModel.value || undefined,
        session_id: currentSessionId.value || undefined,
        skill_slug: options.skill_slug ?? null,
        effort: options.effort ?? null,
      })
      stopLiveUpdates()
      currentSessionId.value = accepted.session_id
      streamingText.value = ''
      streamingThinkingText.value = ''
      streamingThinkingText.value = ''
      void loadSessions(projectId).catch(() => {})
      try {
        currentSession.value = await agentApi.getAgentSession(projectId, accepted.session_id)
      } catch {
        // 后台任务刚启动时快照可能尚不可读,交给流/轮询补齐
      }
      openStream(projectId, accepted.session_id)
      return accepted
    } finally {
      sending.value = false
    }
  }

  async function archiveSession(projectId: string, sessionId: string) {
    await agentApi.archiveAgentSession(projectId, sessionId)
    await loadSessions(projectId)
    if (currentSessionId.value === sessionId) {
      startNewSession()
    }
  }

  async function unarchiveSession(projectId: string, sessionId: string) {
    await agentApi.unarchiveAgentSession(projectId, sessionId)
    await loadSessions(projectId)
  }

  async function deleteSession(projectId: string, sessionId: string) {
    await agentApi.deleteAgentSession(projectId, sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    if (currentSessionId.value === sessionId) {
      startNewSession()
    }
  }

  async function cancelCurrentSession(projectId: string) {
    const sessionId = currentSessionId.value
    if (!sessionId) return
    await agentApi.cancelAgentSession(projectId, sessionId)
  }

  async function renameSession(projectId: string, sessionId: string, title: string) {
    const updated = await agentApi.renameAgentSession(projectId, sessionId, title)
    const idx = sessions.value.findIndex((s) => s.session_id === sessionId)
    if (idx >= 0) {
      sessions.value[idx] = { ...sessions.value[idx], title: updated.title }
    }
    if (currentSessionId.value === sessionId && currentSession.value) {
      currentSession.value = { ...currentSession.value, title: updated.title }
    }
  }

  /** 离开工作区或切换项目时调用,清掉流/轮询与会话状态 */
  function reset() {
    stopLiveUpdates()
    sessions.value = []
    currentSessionId.value = ''
    currentSession.value = null
    streamingText.value = ''
    sending.value = false
    modelTouched.value = false
    selectedModel.value = ''
  }

  return {
    sessions,
    sessionsLoading,
    currentSessionId,
    currentSession,
    sessionLoading,
    sending,
    streamingText,
    streamingThinkingText,
    models,
    modelsLoading,
    selectedModel,
    isSessionRunning,
    loadSessions,
    loadModels,
    applyDefaultModel,
    setSelectedModel,
    selectSession,
    startNewSession,
    sendMessage,
    archiveSession,
    unarchiveSession,
    deleteSession,
    renameSession,
    refreshSnapshot,
    stopLiveUpdates,
    reset,
    cancelCurrentSession,
  }
})
