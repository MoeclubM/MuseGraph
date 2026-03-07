<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import StepProgress from '@/components/simulation/StepProgress.vue'
import ViewModeSwitcher from '@/components/simulation/ViewModeSwitcher.vue'
import SystemLogs from '@/components/simulation/SystemLogs.vue'
import AgentProfiles from '@/components/simulation/AgentProfiles.vue'
import ActionTimeline from '@/components/simulation/ActionTimeline.vue'
import { useToast } from '@/composables/useToast'
import {
  getRunStatus,
  getSimulation,
  getSimulationTimelineEntries,
  prepareSimulation,
  startSimulation,
  stopSimulation,
} from '@/api/simulation'
import { checkReportStatus, generateReport } from '@/api/report'
import type { LogEntry, ViewMode, SimulationAction, OasisAgentProfile } from '@/types'
import {
  Play,
  Square,
  FileText,
  RefreshCw,
  Settings,
  ChevronDown,
  ChevronUp,
  MessageCircle,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const simulationId = computed(() => String(route.params.simulationId || ''))
const simulation = ref<any | null>(null)
const runStatus = ref<Record<string, any> | null>(null)
const actions = ref<SimulationAction[]>([])
const reportState = ref<Record<string, any> | null>(null)
const loading = ref(false)
const preparing = ref(false)
const running = ref(false)
const generating = ref(false)
const viewMode = ref<ViewMode>('split')
const logsExpanded = ref(true)
const logs = ref<LogEntry[]>([])
const selectedAgent = ref<string | null>(null)
const autoPrepareRequestedFor = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const sourceChapterIds = computed<string[]>(() => {
  const meta = simulation.value?.metadata || {}
  const ids = meta?.source_chapter_ids
  return Array.isArray(ids) ? ids.filter((value: string) => !!value) : []
})

const profiles = computed<OasisAgentProfile[]>(() => {
  if (!simulation.value?.profiles) return []
  return simulation.value.profiles.map((profile: any) => ({
    name: profile.name || profile.agent_id,
    role: profile.role || 'participant',
    persona: profile.persona || '',
    stance: profile.stance || 'neutral',
    likely_actions: profile.likely_actions || [],
  }))
})

const simulationStatus = computed(() => String(simulation.value?.status || '').toLowerCase())
const simulationIsRunning = computed(() => Boolean(runStatus.value?.is_running) || runStatus.value?.status === 'running')
const hasPreparedRuntime = computed(() => ['ready', 'completed', 'stopped'].includes(simulationStatus.value))
const canPrepare = computed(() => !!simulation.value && !preparing.value && !running.value && !simulationIsRunning.value)
const canStart = computed(() => !!simulation.value && hasPreparedRuntime.value && !preparing.value && !running.value && !simulationIsRunning.value)
const canStop = computed(() => !!simulation.value && !running.value && simulationIsRunning.value)
const statusHint = computed(() => {
  if (simulationStatus.value === 'created') {
    return 'Preparing the simulation runtime automatically. Start becomes available after participants and runtime settings are ready.'
  }
  if (simulationStatus.value === 'preparing') {
    return 'Simulation runtime is preparing. If it stays in this state, run Prepare again to refresh the latest runtime package.'
  }
  if (simulationIsRunning.value) {
    return 'Simulation is currently running.'
  }
  return ''
})

const currentStep = computed(() => {
  if (!simulation.value) return 2
  if (simulation.value.status === 'created') return 2
  if (simulation.value.status === 'preparing') return 2
  if (simulation.value.status === 'ready') return 2
  if (runStatus.value?.is_running) return 3
  if (reportState.value?.report_id) return 4
  if (simulation.value.status === 'completed') return 4
  return 2
})

const completedSteps = computed(() => {
  const completed: number[] = [1]

  if (['ready', 'completed', 'stopped'].includes(simulationStatus.value)) {
    completed.push(2)
  }
  if (runStatus.value?.current_round > 0 && !runStatus.value?.is_running) {
    completed.push(3)
  }
  if (reportState.value?.report_id) {
    completed.push(4)
  }

  return completed
})

function addLog(level: LogEntry['level'], message: string, source?: string) {
  logs.value.push({
    id: Date.now().toString() + Math.random().toString(36).slice(2, 5),
    timestamp: new Date().toISOString(),
    level,
    message,
    source,
  })
}

async function loadData() {
  if (!simulationId.value) return
  let shouldAutoPrepare = false
  loading.value = true
  try {
    simulation.value = await getSimulation(simulationId.value)
    runStatus.value = await getRunStatus(simulationId.value)
    const actionsData = await getSimulationTimelineEntries(simulationId.value, { limit: 100, offset: 0 })
    actions.value = actionsData as SimulationAction[]
    reportState.value = await checkReportStatus(simulationId.value)

    shouldAutoPrepare = simulation.value?.status === 'created' && autoPrepareRequestedFor.value !== simulationId.value
    addLog('success', 'Data refreshed')
  } catch (error: any) {
    addLog('error', `Load failed: ${error.message}`)
  } finally {
    loading.value = false
  }
  if (shouldAutoPrepare) {
    void handlePrepare({ auto: true })
  }
}

async function handlePrepare(options: { auto?: boolean } = {}) {
  if (!simulationId.value || preparing.value) return
  if (!options.auto && !canPrepare.value) return
  if (options.auto) {
    autoPrepareRequestedFor.value = simulationId.value
    addLog('info', 'Created simulation detected. Starting automatic prepare...')
  } else {
    addLog('info', 'Preparing simulation runtime...')
  }
  preparing.value = true
  try {
    const result = await prepareSimulation({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    if (result.already_prepared) {
      addLog('success', 'Simulation runtime is already prepared')
      if (!options.auto) {
        toast.success('Simulation runtime is already prepared')
      }
    } else {
      addLog('success', 'Prepare task started')
      if (!options.auto) {
        toast.success('Prepare task started')
      }
    }
    await loadData()
  } catch (error: any) {
    addLog('error', `Prepare failed: ${error.message}`)
    toast.error(options.auto ? 'Automatic prepare failed' : 'Prepare failed')
  } finally {
    preparing.value = false
  }
}

async function handleStart() {
  if (!canStart.value) {
    const message = statusHint.value || 'Prepare the simulation before starting.'
    addLog('warning', message)
    toast.error(message)
    return
  }
  running.value = true
  addLog('info', 'Starting simulation...')
  try {
    await startSimulation({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    addLog('success', 'Simulation run completed')
    toast.success('Simulation run completed')
    await loadData()
  } catch (error: any) {
    addLog('error', `Run failed: ${error.message}`)
    toast.error('Run failed')
  } finally {
    running.value = false
  }
}

async function handleStop() {
  if (!canStop.value) {
    const message = 'No active simulation run to stop.'
    addLog('warning', message)
    toast.error(message)
    return
  }
  running.value = true
  addLog('warning', 'Stopping simulation...')
  try {
    await stopSimulation({ simulation_id: simulationId.value })
    addLog('success', 'Simulation stopped')
    toast.success('Simulation stopped')
    await loadData()
  } catch (error: any) {
    addLog('error', `Stop failed: ${error.message}`)
  } finally {
    running.value = false
  }
}

async function handleGenerateReport() {
  generating.value = true
  addLog('info', 'Generating report...')
  try {
    const result = await generateReport({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    addLog('success', 'Report generated')
    toast.success('Report generated')
    if (result.report_id) {
      await router.push(`/report/${result.report_id}`)
      return
    }
    await loadData()
  } catch (error: any) {
    addLog('error', `Report generation failed: ${error.message}`)
    toast.error('Report generation failed')
  } finally {
    generating.value = false
  }
}

function handleAgentSelect(agent: OasisAgentProfile) {
  selectedAgent.value = agent.name
  addLog('info', `Selected participant: ${agent.name}`, 'interaction')
}

onMounted(() => {
  addLog('info', 'Simulation view loaded')
  void loadData()
  timer = setInterval(() => {
    void loadData()
  }, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <AppLayout>
    <template #sidebar>
      <AppSidebar :active-id="simulation?.project_id" />
    </template>
    <div class="space-y-5">
      <Card>
        <div class="space-y-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Scenario Simulation {{ simulationId.slice(0, 8) }}...</h1>
              <p class="text-sm text-stone-500 dark:text-zinc-400">
                Status: <span class="font-medium capitalize">{{ simulation?.status || '-' }}</span>
              </p>
              <p class="text-xs text-stone-500 dark:text-zinc-500">
                Run: {{ runStatus?.status || '-' }} · Round {{ runStatus?.current_round || 0 }}/{{ runStatus?.total_rounds || 0 }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                @click="router.push({
                  path: `/projects/${simulation?.project_id}`,
                })"
              >
                Back to Project
              </Button>
              <Button variant="secondary" :loading="preparing" :disabled="!canPrepare" @click="handlePrepare()">
                <Settings class="h-4 w-4" />
                Prepare
              </Button>
              <Button :loading="running" :disabled="!canStart" @click="handleStart">
                <Play class="h-4 w-4" />
                Start
              </Button>
              <Button variant="danger" :loading="running" :disabled="!canStop" @click="handleStop">
                <Square class="h-4 w-4" />
                Stop
              </Button>
              <Button variant="ghost" @click="router.push(`/simulation/${simulationId}/start`)">
                Open Run Monitor
              </Button>
            </div>
          </div>
          <p v-if="statusHint" class="text-xs text-stone-500 dark:text-zinc-400">
            {{ statusHint }}
          </p>

          <div class="border-t border-stone-300/80 pt-4 dark:border-zinc-700/50">
            <StepProgress
              :current-step="currentStep"
              :completed-steps="completedSteps"
              :project-has-graph="true"
              :simulation-status="simulation?.status"
            />
          </div>
        </div>
      </Card>

      <div class="grid grid-cols-1 gap-4" :class="{ 'lg:grid-cols-2': viewMode === 'split' }">
        <Card v-if="viewMode !== 'graph'">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">
              Participants
            </h2>
            <ViewModeSwitcher :mode="viewMode" @update:mode="viewMode = $event" />
          </div>
          <AgentProfiles
            :profiles="profiles"
            :selected-agent="selectedAgent"
            :interactive="true"
            @select="handleAgentSelect"
          />
        </Card>

        <Card>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">
              Event Timeline
            </h2>
            <div class="flex items-center gap-2">
              <ViewModeSwitcher v-if="viewMode === 'graph'" :mode="viewMode" @update:mode="viewMode = $event" />
              <Button variant="ghost" size="sm" :loading="loading" @click="loadData">
                <RefreshCw class="h-3 w-3" />
              </Button>
            </div>
          </div>
          <ActionTimeline
            :actions="actions"
            max-height="400px"
          />
        </Card>
      </div>

      <Card>
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">Reports and Follow-up</h2>
          <div class="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" size="sm" :loading="generating" @click="handleGenerateReport">
              <FileText class="h-3 w-3" />
              Generate Report
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/report/${reportState.report_id}`)"
            >
              Open Report
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/interaction/${reportState.report_id}`)"
            >
              <MessageCircle class="h-3 w-3" />
              Open Discussion
            </Button>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
          <div class="rounded-lg border border-stone-300/80 bg-stone-100/70 p-3 dark:border-zinc-700/50 dark:bg-zinc-800/50">
            <div class="mb-1 text-xs text-stone-500 dark:text-zinc-400">Report Status</div>
            <div class="font-medium text-stone-800 dark:text-zinc-100">{{ reportState?.status || 'Not generated' }}</div>
          </div>
          <div class="rounded-lg border border-stone-300/80 bg-stone-100/70 p-3 dark:border-zinc-700/50 dark:bg-zinc-800/50">
            <div class="mb-1 text-xs text-stone-500 dark:text-zinc-400">Participant Count</div>
            <div class="font-medium text-stone-800 dark:text-zinc-100">{{ profiles.length }} active</div>
          </div>
          <div class="rounded-lg border border-stone-300/80 bg-stone-100/70 p-3 dark:border-zinc-700/50 dark:bg-zinc-800/50">
            <div class="mb-1 text-xs text-stone-500 dark:text-zinc-400">Environment Status</div>
            <div class="font-medium capitalize text-stone-800 dark:text-zinc-100">{{ simulation?.env_status?.status || 'Unknown' }}</div>
          </div>
        </div>
      </Card>

      <Card>
        <Button
          variant="ghost"
          class="h-auto w-full justify-between px-2 py-1.5"
          @click="logsExpanded = !logsExpanded"
        >
          <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">System Logs</h2>
          <component :is="logsExpanded ? ChevronUp : ChevronDown" class="h-4 w-4 text-stone-500 dark:text-zinc-400" />
        </Button>
        <div v-if="logsExpanded" class="mt-3">
          <SystemLogs :logs="logs" max-height="250px" />
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
