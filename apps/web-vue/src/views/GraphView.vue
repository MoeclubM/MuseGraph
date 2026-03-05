<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import Button from '@/components/ui/Button.vue'
import { getVisualization } from '@/api/graph'
import type { GraphData } from '@/types'
import { ArrowLeft, Maximize2, Minimize2 } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.id as string)
const graphData = ref<GraphData>({ nodes: [], edges: [] })
const loading = ref(true)
const loadError = ref<string | null>(null)
const showSidebar = ref(true)

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

async function loadGraph() {
  loading.value = true
  loadError.value = null
  try {
    graphData.value = await getVisualization(projectId.value)
  } catch (e: any) {
    graphData.value = { nodes: [], edges: [] }
    loadError.value = e?.response?.data?.detail || e?.response?.data?.message || e?.message || 'Failed to load graph visualization'
  } finally {
    loading.value = false
  }
}

onMounted(loadGraph)
</script>

<template>
  <div class="flex h-screen flex-col bg-[#f7f3e8] dark:bg-zinc-900">
    <!-- Top bar -->
    <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-stone-300/80 bg-[#f7f3e8]/90 px-4 py-2 backdrop-blur-sm dark:border-zinc-700/50 dark:bg-zinc-900/80">
      <div class="flex min-w-0 items-center gap-3">
        <Button variant="ghost" size="sm" @click="router.push(`/projects/${projectId}`)">
          <ArrowLeft class="w-4 h-4" />
          Back to Project
        </Button>
        <span class="text-sm text-stone-600 dark:text-zinc-400">Knowledge Graph</span>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <span class="text-xs text-stone-500 dark:text-zinc-500">
          {{ graphData.nodes.length }} nodes, {{ graphData.edges.length }} edges
        </span>
        <Button variant="ghost" size="sm" @click="showSidebar = !showSidebar">
          <Minimize2 v-if="showSidebar" class="w-4 h-4" />
          <Maximize2 v-else class="w-4 h-4" />
        </Button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Graph -->
      <div class="flex-1 relative">
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center">
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
        </div>
        <div v-else-if="loadError" class="absolute inset-0 flex items-center justify-center">
          <div class="text-center max-w-[440px] px-4">
            <p class="text-red-700 dark:text-red-300 mb-2">Failed to load graph data</p>
            <p class="text-xs text-stone-500 dark:text-zinc-500 mb-4 break-words">{{ loadError }}</p>
            <div class="flex items-center justify-center gap-2">
              <Button variant="secondary" @click="loadGraph">Retry</Button>
              <Button variant="ghost" @click="router.push(`/projects/${projectId}`)">
                Back to Project
              </Button>
            </div>
          </div>
        </div>
        <div v-else-if="graphData.nodes.length === 0" class="absolute inset-0 flex items-center justify-center">
          <div class="text-center">
            <p class="text-stone-500 dark:text-zinc-500 mb-4">No graph data available</p>
            <Button variant="secondary" @click="router.push(`/projects/${projectId}`)">
              Go back and build a graph
            </Button>
          </div>
        </div>
        <GraphPanel v-else :data="graphData" class="w-full h-full" />
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
          class="w-80 shrink-0 border-l border-stone-300/80 dark:border-zinc-700/50 bg-[#efe8da]/80 dark:bg-zinc-900/80 p-4 overflow-y-auto"
        >
          <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-4">Search Graph</h3>
          <GraphSearch :project-id="projectId" />

          <div v-if="graphData.nodes.length > 0" class="mt-6">
            <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-3">Entities ({{ graphData.nodes.length }})</h3>
            <div class="space-y-1 max-h-80 overflow-y-auto">
              <div
                v-for="node in graphData.nodes"
                :key="node.id"
                class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-stone-200 dark:hover:bg-zinc-800 transition-colors"
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
