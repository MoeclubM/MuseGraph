<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import ActionTimeline from '@/components/simulation/ActionTimeline.vue'
import SystemLogs from '@/components/simulation/SystemLogs.vue'
import { getRunStatusDetail, getSimulationActions, stopSimulation } from '@/api/simulation'
import type { LogEntry, SimulationAction } from '@/types'
import {
  Square,
  RefreshCw,
  Download,
  ChevronUp,
  ChevronDown,
  Pause,
  Play,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const simulationId = String(route.params.simulationId || '')
const detail = ref<Record<string, any> | null>(null)
const actions = ref<SimulationAction[]>([])
const loading = ref(false)
const logsExpanded = ref(false)
const logs = ref<LogEntry[]>([])
const isPaused = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const currentRound = computed(() => detail.value?.run_state?.current_round || 0)
const totalRounds = computed(() => detail.value?.run_state?.total_rounds || 0)
const roundProgress = computed(() => {
  if (totalRounds.value === 0) return 0
  return (currentRound.value / totalRounds.value) * 100
})

const isRunning = computed(() => detail.value?.run_state?.is_running || false)

function addLog(level: LogEntry['level'], message: string, source?: string) {
  logs.value.push({
    id: Date.now().toString() + Math.random().toString(36).slice(2, 5),
    timestamp: new Date().toISOString(),
    level,
    message,
    source,
  })
  // Keep only last 100 logs
  if (logs.value.length > 100) {
    logs.value = logs.value.slice(-100)
  }
}

async function loadData() {
  if (!simulationId) return
  loading.value = true
  try {
    detail.value = await getRunStatusDetail(simulationId)
    const actionsData = await getSimulationActions(simulationId, { limit: 200, offset: 0 })
    actions.value = actionsData as SimulationAction[]

    if (isRunning.value && !isPaused.value) {
      addLog('info', `Round ${currentRound.value}/${totalRounds.value} 进行中...`)
    }
  } catch (error: any) {
    addLog('error', `加载失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function handleStop() {
  addLog('warning', '正在停止模拟...')
  try {
    await stopSimulation({ simulation_id: simulationId })
    addLog('success', '模拟已停止')
    await loadData()
  } catch (error: any) {
    addLog('error', `停止失败：${error.message}`)
  }
}

function handlePause() {
  isPaused.value = !isPaused.value
  addLog('info', isPaused.value ? '已暂停刷新' : '已恢复刷新')
}

function handleExport(format: 'json' | 'csv') {
  const data = actions.value
  let content: string
  let filename: string

  if (format === 'json') {
    content = JSON.stringify(data, null, 2)
    filename = `simulation-${simulationId.slice(0, 8)}-actions.json`
  } else {
    // CSV format
    const headers = ['action_id', 'round_num', 'agent', 'action_type', 'summary', 'platform', 'created_at']
    const rows = data.map(a => headers.map(h => `"${String((a as any)[h] || '').replace(/"/g, '""')}"`).join(','))
    content = [headers.join(','), ...rows].join('\n')
    filename = `simulation-${simulationId.slice(0, 8)}-actions.csv`
  }

  const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)

  addLog('success', `已导出 ${format.toUpperCase()} 文件`)
}

onMounted(() => {
  addLog('info', '运行监控已启动')
  void loadData()
  timer = setInterval(() => {
    if (!isPaused.value) {
      void loadData()
    }
  }, 2000) // 2秒轮询
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <AppLayout>
    <div class="space-y-5">
      <!-- Header Card -->
      <Card>
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1">
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Simulation Run Monitor</h1>
            <p class="text-sm text-stone-500 dark:text-zinc-400 font-mono">{{ simulationId }}</p>

            <!-- Round Progress -->
            <div class="mt-4">
              <div class="flex items-center justify-between mb-2">
                <span class="text-sm text-stone-700 dark:text-zinc-300">
                  Round {{ currentRound }} / {{ totalRounds }}
                </span>
                <span class="text-xs text-stone-500 dark:text-zinc-500">{{ Math.round(roundProgress) }}%</span>
              </div>
              <div class="h-2 bg-stone-300 dark:bg-zinc-700 rounded-full overflow-hidden">
                <div
                  class="h-full bg-gradient-to-r from-[#FF5722] to-orange-400 transition-all duration-500"
                  :style="{ width: `${roundProgress}%` }"
                />
              </div>
            </div>

            <!-- Status indicators -->
            <div class="mt-3 flex items-center gap-4 text-xs">
              <span
                :class="[
                  'inline-flex items-center gap-1.5 px-2 py-1 rounded',
                  isRunning
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : 'bg-stone-200 text-stone-600 dark:bg-zinc-700 dark:text-zinc-400'
                ]"
              >
                <span
                  :class="[
                    'w-2 h-2 rounded-full',
                    isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-stone-500 dark:bg-zinc-500'
                  ]"
                />
                {{ isRunning ? 'Running' : 'Stopped' }}
              </span>
              <span class="text-stone-500 dark:text-zinc-500">
                {{ actions.length }} actions
              </span>
            </div>
          </div>

          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" @click="router.push(`/simulation/${simulationId}`)">
              返回 Simulation
            </Button>
            <Button
              variant="secondary"
              @click="handlePause"
            >
              <component :is="isPaused ? Play : Pause" class="w-4 h-4" />
              {{ isPaused ? '恢复' : '暂停' }}
            </Button>
            <Button variant="danger" @click="handleStop">
              <Square class="w-4 h-4" />
              停止
            </Button>
            <Button variant="ghost" :loading="loading" @click="loadData">
              <RefreshCw class="w-4 h-4" />
            </Button>
          </div>
        </div>
      </Card>

      <!-- Dual Platform Timeline -->
      <Card>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">
            Live Action Feed
          </h2>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" size="sm" @click="handleExport('json')">
              <Download class="w-3 h-3" />
              JSON
            </Button>
            <Button variant="ghost" size="sm" @click="handleExport('csv')">
              <Download class="w-3 h-3" />
              CSV
            </Button>
          </div>
        </div>

        <ActionTimeline
          :actions="actions"
          platform="all"
          :group-by-round="true"
          max-height="500px"
        />
      </Card>

      <!-- System Logs (Collapsible) -->
      <Card>
        <Button
          variant="ghost"
          class="h-auto w-full justify-between px-2 py-1.5"
          @click="logsExpanded = !logsExpanded"
        >
          <h2 class="text-sm font-medium text-stone-600 dark:text-zinc-300 uppercase tracking-wider">
            System Logs ({{ logs.length }})
          </h2>
          <component :is="logsExpanded ? ChevronUp : ChevronDown" class="w-4 h-4 text-stone-500 dark:text-zinc-400" />
        </Button>
        <div v-if="logsExpanded" class="mt-3">
          <SystemLogs :logs="logs" max-height="200px" />
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
