<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import ActionTimeline from '@/components/simulation/ActionTimeline.vue'
import SystemLogs from '@/components/simulation/SystemLogs.vue'
import { getRunStatusDetail, getSimulationTimelineEntries, stopSimulation } from '@/api/simulation'
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
  if (logs.value.length > 100) {
    logs.value = logs.value.slice(-100)
  }
}

async function loadData() {
  if (!simulationId) return
  loading.value = true
  try {
    detail.value = await getRunStatusDetail(simulationId)
    const actionsData = await getSimulationTimelineEntries(simulationId, { limit: 200, offset: 0 })
    actions.value = actionsData as SimulationAction[]

    if (isRunning.value && !isPaused.value) {
      addLog('info', `Iteration ${currentRound.value}/${totalRounds.value} in progress...`)
    }
  } catch (error: any) {
    addLog('error', `Load failed: ${error.message}`)
  } finally {
    loading.value = false
  }
}

async function handleStop() {
  addLog('warning', 'Stopping scenario run...')
  try {
    await stopSimulation({ simulation_id: simulationId })
    addLog('success', 'Scenario run stopped')
    await loadData()
  } catch (error: any) {
    addLog('error', `Stop failed: ${error.message}`)
  }
}

function handlePause() {
  isPaused.value = !isPaused.value
  addLog('info', isPaused.value ? 'Auto refresh paused' : 'Auto refresh resumed')
}

function handleExport(format: 'json' | 'csv') {
  const data = actions.value
  let content: string
  let filename: string

  if (format === 'json') {
    content = JSON.stringify(data, null, 2)
    filename = `scenario-run-${simulationId.slice(0, 8)}-timeline.json`
  } else {
    const headers = ['action_id', 'round_num', 'agent', 'action_kind', 'action_label', 'summary', 'created_at']
    const rows = data.map((action) => headers.map((header) => `"${String((action as any)[header] || '').replace(/"/g, '""')}"`).join(','))
    content = [headers.join(','), ...rows].join('\n')
    filename = `scenario-run-${simulationId.slice(0, 8)}-timeline.csv`
  }

  const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)

  addLog('success', `Exported ${format.toUpperCase()} timeline file`)
}

onMounted(() => {
  addLog('info', 'Scenario run monitor started')
  void loadData()
  timer = setInterval(() => {
    if (!isPaused.value) {
      void loadData()
    }
  }, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <AppLayout>
    <div class="muse-page-shell muse-page-shell-wide">
      <section class="muse-page-header">
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1">
            <h1 class="text-xl font-semibold text-stone-800 dark:text-zinc-100">Scenario Execution Monitor</h1>
            <p class="font-mono text-sm text-stone-500 dark:text-zinc-400">{{ simulationId }}</p>

            <div class="mt-4">
              <div class="mb-2 flex items-center justify-between">
                <span class="text-sm text-stone-700 dark:text-zinc-300">
                  Iteration {{ currentRound }} / {{ totalRounds }}
                </span>
                <span class="text-xs text-stone-500 dark:text-zinc-500">{{ Math.round(roundProgress) }}%</span>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-stone-300 dark:bg-zinc-700">
                <div
                  class="h-full bg-amber-600 transition-all duration-500"
                  :style="{ width: `${roundProgress}%` }"
                />
              </div>
            </div>

            <div class="mt-3 flex items-center gap-4 text-xs">
              <span
                :class="[
                  'inline-flex items-center gap-1.5 rounded px-2 py-1',
                  isRunning
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : 'bg-stone-200 text-stone-600 dark:bg-zinc-700 dark:text-zinc-400',
                ]"
              >
                <span
                  :class="[
                    'h-2 w-2 rounded-full',
                    isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-stone-500 dark:bg-zinc-500',
                  ]"
                />
                {{ isRunning ? 'Running' : 'Stopped' }}
              </span>
              <span class="text-stone-500 dark:text-zinc-500">
                {{ actions.length }} timeline entries
              </span>
            </div>
          </div>

          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" @click="router.push(`/simulation/${simulationId}`)">
              Back to Overview
            </Button>
            <Button variant="secondary" @click="handlePause">
              <component :is="isPaused ? Play : Pause" class="h-4 w-4" />
              {{ isPaused ? 'Resume' : 'Pause' }}
            </Button>
            <Button variant="danger" @click="handleStop">
              <Square class="h-4 w-4" />
              Stop Run
            </Button>
            <Button variant="ghost" :loading="loading" @click="loadData">
              <RefreshCw class="h-4 w-4" />
            </Button>
            </div>
          </div>
      </section>

      <Card>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">
            Analysis Timeline
          </h2>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" size="sm" @click="handleExport('json')">
              <Download class="h-3 w-3" />
              JSON
            </Button>
            <Button variant="ghost" size="sm" @click="handleExport('csv')">
              <Download class="h-3 w-3" />
              CSV
            </Button>
          </div>
        </div>

        <ActionTimeline
          :actions="actions"
          :group-by-round="true"
          max-height="500px"
        />
      </Card>

      <Card>
        <Button
          variant="ghost"
          class="h-auto w-full justify-between px-2 py-1.5"
          @click="logsExpanded = !logsExpanded"
        >
          <h2 class="text-sm font-medium uppercase tracking-wider text-stone-600 dark:text-zinc-300">
            System Logs ({{ logs.length }})
          </h2>
          <component :is="logsExpanded ? ChevronUp : ChevronDown" class="h-4 w-4 text-stone-500 dark:text-zinc-400" />
        </Button>
        <div v-if="logsExpanded" class="mt-3">
          <SystemLogs :logs="logs" max-height="200px" />
        </div>
      </Card>
    </div>
  </AppLayout>
</template>
