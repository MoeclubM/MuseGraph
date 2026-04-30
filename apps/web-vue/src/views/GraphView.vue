<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import Button from '@/components/ui/Button.vue'
import { getOasisTaskStatus, getVisualization, listGraphTasks } from '@/api/graph'
import type { GraphData, OasisTask } from '@/types'
import { ArrowLeft, Maximize2, Minimize2 } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.id as string)
const graphData = ref<GraphData>({ nodes: [], edges: [] })
const loading = ref(true)
const loadError = ref<string | null>(null)
const showSidebar = ref(true)
const graphTask = ref<OasisTask | null>(null)
const taskError = ref<string | null>(null)
let graphTaskTimer: ReturnType<typeof setInterval> | null = null

const TASK_POLL_MS = 3000

const NODE_COLORS: Record<string, string> = {
  Entity: '#a16207',
  EntityType: '#0f766e',
  TextSummary: '#be185d',
  DocumentChunk: '#6d28d9',
  TextDocument: '#78716c',
  PERSON: '#2563eb',
  PLACE: '#0f766e',
  ORGANIZATION: '#c2410c',
  CONCEPT: '#7c3aed',
  EVENT: '#dc2626',
  OBJECT: '#0891b2',
  DATE: '#db2777',
  DEFAULT: '#a8a29e',
}

function normalizeNodeType(type: string): string {
  const raw = String(type || '').trim()
  if (!raw) return 'Entity'
  const key = raw.replace(/[^a-zA-Z0-9_]/g, '').toLowerCase()
  if (key === 'entitytype') return 'EntityType'
  if (key === 'textsummary' || key === 'summary') return 'TextSummary'
  if (key === 'documentchunk' || key === 'chunk') return 'DocumentChunk'
  if (key === 'textdocument' || key === 'document') return 'TextDocument'
  if (key === 'entity') return 'Entity'
  return raw
}

function getNodeColor(type: string): string {
  const normalized = normalizeNodeType(type)
  return NODE_COLORS[normalized] || NODE_COLORS[normalized.toUpperCase()] || NODE_COLORS.DEFAULT
}

function parseError(e: any, fallback: string): string {
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback
}

function isRunningTaskStatus(status: string | undefined): boolean {
  const normalized = String(status || '').toLowerCase()
  return normalized === 'pending' || normalized === 'processing'
}

const graphBuildRunning = computed(() => graphTask.value?.task_type === 'graph_build' && isRunningTaskStatus(graphTask.value.status))
const graphBuildProgress = computed(() => Math.max(0, Math.min(100, Number(graphTask.value?.progress || 0))))
const graphBuildMessage = computed(() => graphTask.value?.message || (graphBuildRunning.value ? 'Building knowledge graph...' : ''))
const graphBuildStatusLabel = computed(() => String(graphTask.value?.status || '').toLowerCase())
const graphPreviewTaskId = computed(() => graphBuildRunning.value ? graphTask.value?.task_id : undefined)

async function loadGraph(options: { preserveOnError?: boolean; previewTaskId?: string } = {}) {
  if (!options.preserveOnError) {
    loading.value = true
    loadError.value = null
  }
  try {
    graphData.value = await getVisualization(projectId.value, { previewTaskId: options.previewTaskId })
    loadError.value = null
  } catch (e: any) {
    if (!options.preserveOnError) {
      graphData.value = { nodes: [], edges: [] }
      loadError.value = parseError(e, 'Failed to load graph visualization')
    }
  } finally {
    if (!options.preserveOnError) loading.value = false
  }
}

function stopGraphTaskPolling() {
  if (graphTaskTimer) {
    clearInterval(graphTaskTimer)
    graphTaskTimer = null
  }
}

async function pollGraphTask(taskId: string) {
  try {
    const response = await getOasisTaskStatus(projectId.value, taskId)
    graphTask.value = response.task
    taskError.value = null
    if (graphBuildRunning.value) {
      await loadGraph({ preserveOnError: true, previewTaskId: response.task.task_id })
      return
    }
    stopGraphTaskPolling()
    await loadGraph({ preserveOnError: true })
  } catch (e: any) {
    taskError.value = parseError(e, 'Failed to load graph build progress')
  }
}

function startGraphTaskPolling(taskId: string) {
  stopGraphTaskPolling()
  graphTaskTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    void pollGraphTask(taskId)
  }, TASK_POLL_MS)
}

async function loadLatestGraphTask() {
  try {
    const response = await listGraphTasks(projectId.value, { task_type: 'graph_build', limit: 10 })
    const tasks = [...(response.tasks || [])].sort((a, b) => {
      const at = Date.parse(a.created_at || '') || 0
      const bt = Date.parse(b.created_at || '') || 0
      return bt - at
    })
    graphTask.value = tasks.find((task) => isRunningTaskStatus(task.status)) || tasks[0] || null
    taskError.value = null
  } catch (e: any) {
    taskError.value = parseError(e, 'Failed to load graph build progress')
  }
}

async function initializeGraphView() {
  stopGraphTaskPolling()
  await loadLatestGraphTask()
  await loadGraph({ previewTaskId: graphPreviewTaskId.value })
  if (graphPreviewTaskId.value) startGraphTaskPolling(graphPreviewTaskId.value)
}

onMounted(() => {
  void initializeGraphView()
})

onUnmounted(() => {
  stopGraphTaskPolling()
})
</script>

<template>
  <div class="flex h-screen flex-col bg-[#f7f3e8] dark:bg-zinc-900">
    <!-- Top bar -->
    <div class="px-4 pt-4">
      <div class="muse-surface flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-md px-4 py-3">
      <div class="flex min-w-0 items-center gap-3">
        <Button variant="ghost" size="sm" @click="router.push(`/projects/${projectId}`)">
          <ArrowLeft class="w-4 h-4" />
          Back to Project
        </Button>
        <span class="text-sm text-stone-600 dark:text-zinc-400">Knowledge Graph</span>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <span
          v-if="graphTask"
          class="rounded-full border border-amber-300/70 bg-amber-50 px-2.5 py-1 text-xs text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200"
        >
          Graph Build: {{ graphBuildStatusLabel }} · {{ graphBuildProgress }}%
        </span>
        <span class="text-xs text-stone-500 dark:text-zinc-500">
          {{ graphData.nodes.length }} nodes, {{ graphData.edges.length }} edges
        </span>
        <Button variant="ghost" size="sm" @click="showSidebar = !showSidebar">
          <Minimize2 v-if="showSidebar" class="w-4 h-4" />
          <Maximize2 v-else class="w-4 h-4" />
        </Button>
      </div>
      </div>
    </div>

    <!-- Content -->
    <div class="flex flex-1 gap-4 overflow-hidden px-4 pb-4 pt-4">
      <!-- Graph -->
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <div
          v-if="graphBuildRunning"
          class="shrink-0 rounded-md border border-amber-300/70 bg-amber-50 px-4 py-3 shadow-sm dark:border-amber-700/60 dark:bg-amber-950/40"
        >
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span class="font-medium text-amber-800 dark:text-amber-200">
              Graph build in progress · {{ graphBuildProgress }}%
            </span>
            <span class="text-amber-700 dark:text-amber-300">
              {{ graphData.nodes.length > 0 ? 'Live preview is updating' : 'Waiting for preview data' }}
            </span>
          </div>
          <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-amber-200/80 dark:bg-amber-950">
            <div class="h-full rounded-full bg-amber-600 transition-all" :style="{ width: `${graphBuildProgress}%` }" />
          </div>
          <p v-if="graphBuildMessage" class="mt-2 text-xs text-amber-800 dark:text-amber-200">{{ graphBuildMessage }}</p>
          <p v-if="taskError" class="mt-2 text-xs text-red-700 dark:text-red-300">{{ taskError }}</p>
        </div>
        <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg">
          <div v-if="loading" class="absolute inset-0 flex items-center justify-center">
            <div class="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
          </div>
          <div v-else-if="loadError" class="absolute inset-0 flex items-center justify-center">
            <div class="text-center max-w-[440px] px-4">
              <p class="text-red-700 dark:text-red-300 mb-2">Failed to load graph data</p>
              <p class="text-xs text-stone-500 dark:text-zinc-500 mb-4 break-words">{{ loadError }}</p>
              <div class="flex items-center justify-center gap-2">
                <Button variant="secondary" @click="initializeGraphView">Retry</Button>
                <Button variant="ghost" @click="router.push(`/projects/${projectId}`)">
                  Back to Project
                </Button>
              </div>
            </div>
          </div>
          <div v-else-if="graphData.nodes.length === 0" class="absolute inset-0 flex items-center justify-center">
            <div class="text-center">
              <p class="text-stone-500 dark:text-zinc-500 mb-4">
                {{ graphBuildRunning ? 'Graph build is running. Preview data will appear here when Graphiti writes the first nodes.' : 'No graph data available' }}
              </p>
              <Button v-if="!graphBuildRunning" variant="secondary" @click="router.push(`/projects/${projectId}`)">
                Go back and build a graph
              </Button>
            </div>
          </div>
          <GraphPanel v-else :data="graphData" class="w-full h-full" />
        </div>
      </div>

      <!-- Sidebar -->
      <Transition
        enter-active-class="transition-all duration-200"
        leave-active-class="transition-all duration-200"
        enter-from-class="translate-x-full opacity-0"
        leave-to-class="translate-x-full opacity-0"
      >
        <div
          v-if="showSidebar"
          class="w-96 max-w-[34vw] shrink-0 overflow-y-auto rounded-md border border-stone-300/80 bg-[#efe8da]/80 p-4 dark:border-zinc-700/50 dark:bg-zinc-900/80"
        >
          <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-4">Search Graph</h3>
          <GraphSearch :project-id="projectId" />

          <div v-if="graphData.nodes.length > 0" class="mt-6">
            <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-3">Entities ({{ graphData.nodes.length }})</h3>
            <div class="space-y-1 max-h-80 overflow-y-auto">
              <div
                v-for="node in graphData.nodes"
                :key="node.id"
                class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-stone-200 dark:hover:bg-zinc-800"
              >
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: getNodeColor(node.type) }"
                />
                <span class="text-stone-700 dark:text-zinc-300 truncate">{{ node.label }}</span>
                <span class="text-xs text-stone-500 dark:text-zinc-500 ml-auto shrink-0">{{ node.type }}</span>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>
