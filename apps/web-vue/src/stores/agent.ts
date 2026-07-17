import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  AgentRun,
  AgentRunEvent,
  AgentRunMode,
  ChangeSet,
  Project,
} from '@/types'
import * as agentApi from '@/api/agent'
import { getModels, type ModelInfo } from '@/api/projects'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'accepting'])

export const useAgentStore = defineStore('agent', () => {
  const runs = ref<AgentRun[]>([])
  const currentRun = ref<AgentRun | null>(null)
  const events = ref<AgentRunEvent[]>([])
  const changeSet = ref<ChangeSet | null>(null)
  const loading = ref(false)
  const submitting = ref(false)
  const models = ref<ModelInfo[]>([])
  const modelsLoading = ref(false)
  const selectedModel = ref('')
  const modelTouched = ref(false)
  let stopStream: (() => void) | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const currentRunId = computed(() => currentRun.value?.id || '')
  const isRunActive = computed(() => ACTIVE_STATUSES.has(currentRun.value?.status || ''))
  const isAwaitingReview = computed(() => currentRun.value?.status === 'awaiting_review')

  function stopLiveUpdates() {
    stopStream?.()
    stopStream = null
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  async function loadRuns(projectId: string) {
    loading.value = true
    try {
      runs.value = await agentApi.listAgentRuns(projectId)
    } finally {
      loading.value = false
    }
  }

  function applyDefaultModel(project?: Project | null) {
    if (modelTouched.value && selectedModel.value) return
    const configured = String(project?.component_models?.operation_agent_task || '').trim()
    selectedModel.value = configured || models.value[0]?.id || ''
  }

  async function loadModels(project?: Project | null) {
    modelsLoading.value = true
    try {
      models.value = await getModels()
      applyDefaultModel(project)
    } finally {
      modelsLoading.value = false
    }
  }

  function setSelectedModel(modelId: string) {
    selectedModel.value = modelId
    modelTouched.value = true
  }

  async function refreshCurrent(projectId: string) {
    const runId = currentRunId.value
    if (!runId) return
    const run = await agentApi.getAgentRun(projectId, runId)
    if (currentRunId.value !== runId) return
    currentRun.value = run
    const index = runs.value.findIndex((item) => item.id === run.id)
    if (index >= 0) runs.value[index] = run
    if (run.status === 'awaiting_review' || run.status === 'completed') {
      changeSet.value = await agentApi.getAgentRunChanges(projectId, runId)
    }
  }

  function openStream(projectId: string, runId: string) {
    stopLiveUpdates()
    const lastEventId = events.value[events.value.length - 1]?.id || 0
    stopStream = agentApi.streamAgentRun(projectId, runId, lastEventId, {
      onEvent: (event) => {
        if (currentRunId.value !== runId) return
        if (!events.value.some((item) => item.id === event.id)) events.value.push(event)
        void refreshCurrent(projectId)
      },
      onClose: (error) => {
        stopStream = null
        if (currentRunId.value !== runId) return
        if (error && isRunActive.value) {
          reconnectTimer = setTimeout(() => openStream(projectId, runId), 1000)
        }
      },
    })
  }

  async function selectRun(projectId: string, runId: string) {
    stopLiveUpdates()
    events.value = []
    changeSet.value = null
    currentRun.value = await agentApi.getAgentRun(projectId, runId)
    if (currentRun.value.status === 'awaiting_review' || currentRun.value.status === 'completed') {
      changeSet.value = await agentApi.getAgentRunChanges(projectId, runId)
    }
    if (ACTIVE_STATUSES.has(currentRun.value.status)) openStream(projectId, runId)
  }

  function startNewRun() {
    stopLiveUpdates()
    currentRun.value = null
    events.value = []
    changeSet.value = null
  }

  async function startRun(
    projectId: string,
    instruction: string,
    options: {
      mode: AgentRunMode
      target_refs: string[]
      skill_slug?: string | null
      effort?: string | null
    },
  ) {
    submitting.value = true
    try {
      const run = await agentApi.startAgentRun(projectId, {
        instruction,
        mode: options.mode,
        target_refs: options.target_refs,
        skill_slug: options.skill_slug,
        effort: options.effort,
        model: selectedModel.value || null,
      })
      runs.value.unshift(run)
      currentRun.value = run
      events.value = []
      changeSet.value = null
      openStream(projectId, run.id)
      return run
    } finally {
      submitting.value = false
    }
  }

  async function cancelCurrent(projectId: string) {
    if (!currentRun.value) return
    currentRun.value = await agentApi.cancelAgentRun(projectId, currentRun.value.id)
    stopLiveUpdates()
  }

  async function reviewCurrent(projectId: string, decision: 'accept' | 'reject') {
    if (!currentRun.value) return
    submitting.value = true
    try {
      currentRun.value = await agentApi.reviewAgentRun(projectId, currentRun.value.id, decision)
      const index = runs.value.findIndex((item) => item.id === currentRun.value?.id)
      if (index >= 0) runs.value[index] = currentRun.value
      return currentRun.value
    } finally {
      submitting.value = false
    }
  }

  function reset() {
    stopLiveUpdates()
    runs.value = []
    currentRun.value = null
    events.value = []
    changeSet.value = null
    modelTouched.value = false
    selectedModel.value = ''
  }

  return {
    runs,
    currentRun,
    currentRunId,
    events,
    changeSet,
    loading,
    submitting,
    models,
    modelsLoading,
    selectedModel,
    isRunActive,
    isAwaitingReview,
    loadRuns,
    loadModels,
    applyDefaultModel,
    setSelectedModel,
    selectRun,
    startNewRun,
    startRun,
    cancelCurrent,
    reviewCurrent,
    refreshCurrent,
    stopLiveUpdates,
    reset,
  }
})
