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
const showSidebar = ref(true)

async function loadGraph() {
  loading.value = true
  try {
    graphData.value = await getVisualization(projectId.value)
  } catch {
    graphData.value = { nodes: [], edges: [] }
  } finally {
    loading.value = false
  }
}

onMounted(loadGraph)
</script>

<template>
  <div class="flex h-screen flex-col bg-slate-900">
    <!-- Top bar -->
    <div class="flex items-center justify-between px-4 py-2 border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm">
      <div class="flex items-center gap-3">
        <Button variant="ghost" size="sm" @click="router.push(`/projects/${projectId}`)">
          <ArrowLeft class="w-4 h-4" />
          Back to Project
        </Button>
        <span class="text-sm text-slate-400">Knowledge Graph</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-500">
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
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
        </div>
        <div v-else-if="graphData.nodes.length === 0" class="absolute inset-0 flex items-center justify-center">
          <div class="text-center">
            <p class="text-slate-500 mb-4">No graph data available</p>
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
          class="w-80 shrink-0 border-l border-slate-700/50 bg-slate-900/80 p-4 overflow-y-auto"
        >
          <h3 class="text-sm font-semibold text-slate-300 mb-4">Search Graph</h3>
          <GraphSearch :project-id="projectId" />

          <div v-if="graphData.nodes.length > 0" class="mt-6">
            <h3 class="text-sm font-semibold text-slate-300 mb-3">Entities ({{ graphData.nodes.length }})</h3>
            <div class="space-y-1 max-h-80 overflow-y-auto">
              <div
                v-for="node in graphData.nodes"
                :key="node.id"
                class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-800 transition-colors"
              >
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{
                    backgroundColor:
                      node.type === 'PERSON' ? '#3b82f6' :
                      node.type === 'PLACE' ? '#10b981' :
                      node.type === 'ORGANIZATION' ? '#f59e0b' :
                      node.type === 'CONCEPT' ? '#8b5cf6' :
                      node.type === 'EVENT' ? '#ef4444' :
                      '#64748b'
                  }"
                />
                <span class="text-slate-300 truncate">{{ node.label }}</span>
                <span class="text-xs text-slate-600 ml-auto shrink-0">{{ node.type }}</span>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>
