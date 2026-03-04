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

  if (simulation.value?.status === 'ready' || simulation.value?.status === 'completed') {
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
  loading.value = true
  try {
    simulation.value = await getSimulation(simulationId.value)
    runStatus.value = await getRunStatus(simulationId.value)
    const actionsData = await getSimulationActions(simulationId.value, { limit: 100, offset: 0 })
    actions.value = actionsData as SimulationAction[]
    reportState.value = await checkReportStatus(simulationId.value)

    // Load interview history
    try {
      interviewHistory.value = await getInterviewHistory({
        simulation_id: simulationId.value,
        limit: 10,
      })
    } catch {
      interviewHistory.value = []
    }

    addLog('success', '数据刷新完成')
  } catch (error: any) {
    addLog('error', `加载失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function handlePrepare() {
  preparing.value = true
  addLog('info', '正在准备环境...')
  try {
    const result = await prepareSimulation({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    if (result.already_prepared) {
      addLog('success', '环境已准备完成')
      toast.success('Simulation 已准备完成')
    } else {
      addLog('success', '准备任务已启动')
      toast.success('准备任务已启动')
    }
    await loadData()
  } catch (error: any) {
    addLog('error', `准备失败：${error.message}`)
    toast.error('准备失败')
  } finally {
    preparing.value = false
  }
}

async function handleStart() {
  running.value = true
  addLog('info', '正在启动模拟...')
  try {
    await startSimulation({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    addLog('success', '模拟运行完成')
    toast.success('Simulation 运行完成')
    await loadData()
  } catch (error: any) {
    addLog('error', `运行失败：${error.message}`)
    toast.error('运行失败')
  } finally {
    running.value = false
  }
}

async function handleStop() {
  running.value = true
  addLog('warning', '正在停止模拟...')
  try {
    await stopSimulation({ simulation_id: simulationId.value })
    addLog('success', '模拟已停止')
    toast.success('Simulation 已停止')
    await loadData()
  } catch (error: any) {
    addLog('error', `停止失败：${error.message}`)
  } finally {
    running.value = false
  }
}

async function handleGenerateReport() {
  generating.value = true
  addLog('info', '正在生成报告...')
  try {
    const result = await generateReport({
      simulation_id: simulationId.value,
      chapter_ids: sourceChapterIds.value.length ? sourceChapterIds.value : undefined,
    })
    addLog('success', '报告生成任务已启动')
    toast.success('报告任务已启动')
    if (result.report_id) {
      await router.push(`/report/${result.report_id}`)
      return
    }
    await loadData()
  } catch (error: any) {
    addLog('error', `生成失败：${error.message}`)
    toast.error('生成报告失败')
  } finally {
    generating.value = false
  }
}

async function handleCloseEnv() {
  addLog('info', '正在关闭环境...')
  try {
    await closeSimulationEnv({ simulation_id: simulationId.value })
    addLog('success', '环境已关闭')
    toast.success('环境已关闭')
    await loadData()
  } catch (error: any) {
    addLog('error', `关闭失败：${error.message}`)
  }
}

function handleAgentSelect(agent: OasisAgentProfile) {
  selectedAgent.value = agent.name
  addLog('info', `已选择 Agent: ${agent.name}`, 'interaction')
}

onMounted(() => {
  addLog('info', '页面加载中...')
  void loadData()
  timer = setInterval(() => {
    void loadData()
  }, 2000) // 2秒轮询
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
                返回项目
              </Button>
              <Button variant="secondary" :loading="preparing" @click="handlePrepare">
                <Settings class="w-4 h-4" />
                准备环境
              </Button>
              <Button :loading="running" @click="handleStart">
                <Play class="w-4 h-4" />
                开始模拟
              </Button>
              <Button variant="danger" :loading="running" @click="handleStop">
                <Square class="w-4 h-4" />
                停止
              </Button>
              <Button variant="ghost" @click="router.push(`/simulation/${simulationId}/start`)">
                运行视图
              </Button>
            </div>
          </div>

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
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">报告 & 互动</h2>
          <div class="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" size="sm" :loading="generating" @click="handleGenerateReport">
              <FileText class="w-3 h-3" />
              生成报告
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/report/${reportState.report_id}`)"
            >
              打开报告
            </Button>
            <Button
              v-if="reportState?.report_id"
              variant="ghost"
              size="sm"
              @click="router.push(`/interaction/${reportState.report_id}`)"
            >
              <MessageCircle class="w-3 h-3" />
              深度互动
            </Button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">报告状态</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium">{{ reportState?.status || '未生成' }}</div>
          </div>
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">访谈记录</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium">{{ interviewHistory.length }} 条</div>
          </div>
          <div class="p-3 rounded-lg bg-stone-100/70 dark:bg-zinc-800/50 border border-stone-300/80 dark:border-zinc-700/50">
            <div class="text-stone-500 dark:text-zinc-400 text-xs mb-1">环境状态</div>
            <div class="text-stone-800 dark:text-zinc-100 font-medium capitalize">{{ simulation?.env_status?.status || '未知' }}</div>
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
