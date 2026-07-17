<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import Button from '@/components/ui/Button.vue'
import { getMemoryVisualization } from '@/api/memory'
import type { GraphData } from '@/types'
import { ArrowLeft, Maximize2, Minimize2 } from '@lucide/vue'

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

function parseError(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return err?.response?.data?.detail || err?.response?.data?.message || err?.message || fallback
}

async function loadGraph() {
  loading.value = true
  loadError.value = null
  try {
    graphData.value = await getMemoryVisualization(projectId.value)
  } catch (e: unknown) {
    graphData.value = { nodes: [], edges: [] }
    loadError.value = parseError(e, 'Failed to load memory graph')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadGraph()
})
</script>

<template>
  <div class="flex h-screen flex-col bg-[#f7f3e8] dark:bg-zinc-900">
    <div class="px-4 pt-4">
      <div class="muse-surface flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-md px-4 py-3">
        <div class="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="sm" @click="router.push(`/projects/${projectId}`)">
            <ArrowLeft class="w-4 h-4" />
            Back to workspace
          </Button>
          <span class="text-sm text-stone-600 dark:text-zinc-400">Cognee graph</span>
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
    </div>

    <div class="flex flex-1 gap-4 overflow-hidden px-4 pb-4 pt-4">
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg">
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
                  Back to workspace
                </Button>
              </div>
            </div>
          </div>
          <div v-else-if="graphData.nodes.length === 0" class="absolute inset-0 flex items-center justify-center">
            <div class="text-center">
              <p class="text-stone-500 dark:text-zinc-500 mb-4">
                No memory graph yet. Build memory from project settings or let the agent write memories.
              </p>
              <Button variant="secondary" @click="router.push(`/projects/${projectId}/settings`)">
                Project settings
              </Button>
            </div>
          </div>
          <GraphPanel v-else :data="graphData" class="w-full h-full" />
        </div>
      </div>

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
          <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-4">Search memory</h3>
          <GraphSearch :project-id="projectId" />

          <div v-if="graphData.nodes.length > 0" class="mt-6">
            <h3 class="text-sm font-semibold text-stone-700 dark:text-zinc-300 mb-3">Legend</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="type in [...new Set(graphData.nodes.map((n) => normalizeNodeType(n.type)))]"
                :key="type"
                class="inline-flex items-center gap-1.5 rounded-full border border-stone-300/70 px-2 py-0.5 text-xs dark:border-zinc-600"
              >
                <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: getNodeColor(type) }" />
                {{ type }}
              </span>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>
