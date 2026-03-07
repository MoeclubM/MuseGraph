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
  closeSimulationEnv,
  getRunStatus,
  getSimulation,
  getSimulationActions,
  prepareSimulation,
  startSimulation,
  stopSimulation,
  getInterviewHistory,
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
const interviewHistory = ref<any[]>([])
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
  return Array.isArray(ids) ? ids.filter((x: string) => !!x) : []
})

const profiles = computed<OasisAgentProfile[]>(() => {
  if (!simulation.value?.profiles) return []
  return simulation.value.profiles.map((p: any) => ({
    name: p.name || p.agent_id,
    role: p.role || 'participant',
    persona: p.persona || '',
    stance: p.stance || 'neutral',
    likely_actions: p.likely_actions || [],
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
    return 'Preparing the simulation runtime automatically. Start becomes available after profiles and config are ready.'
  }
  if (simulationStatus.value === 'preparing') {
    return 'Simulation runtime is preparing. If it stays in this state, use Prepare again to retry with the latest runtime.'
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
  if (interviewHistory.value.length > 0) return 5
  if (simulation.value.status === 'completed') return 4
  return 2
})

const completedSteps = computed(() => {
  const completed: number[] = [1] // Assume graph is complete since we're here

  if (['ready', 'completed', 'stopped'].includes(simulationStatus.value)) {
    completed.push(2)
  }
  if (runStatus.value?.current_round > 0 && !runStatus.value?.is_running) {
    completed.push(3)
  }
  if (reportState.value?.report_id) {
    completed.push(4)
  }
  if (interviewHistory.value.length > 0) {
    completed.push(5)
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
    const actionsData = await getSimulationActions(simulationId.value, { limit: 100, offset: 0 })
    actions.value = actionsData as SimulationAction[]
    reportState.value = await checkReportStatus(simulationId.value)

    try {
      interviewHistory.value = await getInterviewHistory({
        simulation_id: simulationId.value,
        limit: 10,
      })
    } catch {
      interviewHistory.value = []
    }

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
        toast.success('Simulation is already prepared')
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
    toast.error(options.auto ? 'Automatic simulation prepare failed' : 'Prepare failed')
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

async function handleCloseEnv() {
  addLog('info', 'Closing simulation environment...')
  try {
    await closeSimulationEnv({ simulation_id: simulationId.value })
    addLog('success', 'Simulation environment closed')
    toast.success('Simulation environment closed')
    await loadData()
  } catch (error: any) {
    addLog('error', `Close environment failed: ${error.message}`)
  }
}

function handleAgentSelect(agent: OasisAgentProfile) {
  selectedAgent.value = agent.name
  addLog('info', `宸查€夋嫨 Agent: ${agent.name}`, 'interaction')
}

onMounted(() => {
  addLog('info', '椤甸潰鍔犺浇涓?..')
  void loadData()
  timer = setInterval(() => {
    void loadData()
  }, 2000) // 2绉掕疆璇?
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
      <!-- Header Card -->
      <Card>
        <div class="space-y-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Simulation {{ simulationId.slice(0, 8) }}...</h1>
              <p class="text-sm text-stone-500 dark:text-zinc-400">
                Status: <span class="capitalize font-medium">{{ simulation?.status || '-' }}</span>
              </p>
              <p class="text-xs text-stone-500 dark:text-zinc-500">
                Run: {{ runStatus?.status || '-' }} 路 Round {{ runStatus?.current_round || 0 }}/{{ runStatus?.total_rounds || 0 }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                @click="router.push({
                  path: `/projects/${simulation?.project_id}`,
                })"
              >
                杩斿洖椤圭洰
              </Button>
              <Button variant="secondary" :loading="preparing" :disabled="!canPrepare" @click="handlePrepare()">
                <Settings class="w-4 h-4" />
                Prepare
              </Button>
              <Button :loading="running" :disabled="!canStart" @click="handleStart">
                <Play class="w-4 h-4" />
                Start
              </Button>
              <Button variant="danger" :loading="running" :disabled="!canStop" @click="handleStop">
                <Square class="w-4 h-4" />
                Stop
              </Button>
              <Button variant="ghost" @click="router.push(`/simulation/${simulationId}/start`)">
                Open Run View
              </Button>
            </div>
          </div>
          <p v-if="statusHint" class="text-xs text-stone-500 dark:text-zinc-400">
            {{ statusHint }}
          </p>

          <!-- Step Progress -->
          <div class="pt-4 border-t border-stone-300/80 dark:border-zinc-700/50">
            <StepProgress
              :current-step="currentStep"
              :completed-steps="completedSteps"
              :project-has-graph="true"
              :simulation-status="simulation?.status"
            />
          </div>
        </div>
      </Card>

      <!-- Main Content Area -->
      <div class="grid grid-cols-1 gap-4" :class="{ 'lg:grid-cols-2': viewMode === 'split' }">
        <!-- Left Panel: Agent Profiles (split/workbench) or Graph (graph mode) -->
        <Card v-if="viewMode !== 'graph'">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">
              Agent Profiles
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

        <!-- Right Panel: Action Timeline -->
        <Card>
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">
              Action Timeline
            </h2>
            <div class="flex items-center gap-2">
              <ViewModeSwitcher v-if="viewMode === 'graph'" :mode="viewMode" @update:mode="viewMode = $event" />
              <Button variant="ghost" size="sm" :loading="loading" @click="loadData">
                <RefreshCw class="w-3 h-3" />
              </Button>
            </div>
          </div>
          <ActionTimeline
            :actions="actions"
            platform="all"
            max-height="400px"
          />
        </Card>
      </div>

      <!-- Reports Card -->
      <Card>
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">鎶ュ憡 & 浜掑姩</h2>
          <div class="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" size="sm" :loading="generating" @click="handleGenerateReport">
              <FileText class="w-3 h-3" />
              鐢熸垚鎶ュ憡
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/report/${reportState.report_id}`)"
            >
              鎵撳紑鎶ュ憡
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/interaction/${reportState.report_id}`)"
            >
              <MessageCircle class="w-3 h-3" />
              娣卞害浜掑姩
            </Button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">Report Status</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium">{{ reportState?.status || 'Not generated' }}</div>
          </div>
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">璁胯皥璁板綍</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium">{{ interviewHistory.length }} entries</div>
          </div>
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">Environment Status</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium capitalize">{{ simulation?.env_status?.status || '鏈煡' }}</div>
          </div>
        </div>
      </Card>

      <!-- System Logs (Collapsible) -->
      <Card>
        <Button
          variant="ghost"
          class="h-auto w-full justify-between px-2 py-1.5"
          @click="logsExpanded = !logsExpanded"
        >
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">System Logs</h2>
          <component :is="logsExpanded ? ChevronUp : ChevronDown" class="w-4 h-4 text-stone-500 dark:text-zinc-400" />
        </Button>
        <div v-if="logsExpanded" class="mt-3">
          <SystemLogs :logs="logs" max-height="250px" />
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
