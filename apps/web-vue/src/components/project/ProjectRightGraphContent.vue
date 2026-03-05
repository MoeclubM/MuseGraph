<script setup lang="ts">
import type { ModelInfo } from '@/api/projects'
import type {
  GraphData,
  OasisTask,
  ProjectOntology,
} from '@/types'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import ProjectGraphBuildPanel from '@/components/project/ProjectGraphBuildPanel.vue'
import ProjectOasisAnalysisCard from '@/components/project/ProjectOasisAnalysisCard.vue'
import Button from '@/components/ui/Button.vue'
import { Network } from 'lucide-vue-next'

interface GraphBuildSummary {
  status: string
  requestedMode: string
  mode: string
  modeReason: string
  reason: string
  changedCount: number
  addedCount: number
  modifiedCount: number
  removedCount: number
}

const props = defineProps<{
  rightPanelTab: string
  workflowSourceTextLength: number
  ontologyRequirement: string
  modelsLoading: boolean
  models: ModelInfo[]
  ontologyModel: string
  ontologyLoading: boolean
  graphCanBuild: boolean
  ontologyMessage: string
  ontologyProgress: number
  graphParsingFile: string | null
  ontologyError: string | null
  ontologyData: ProjectOntology | null
  hasOntology: boolean
  ontologyMeta: Record<string, unknown> | null
  graphBuildModel: string
  embeddingModels: ModelInfo[]
  graphEmbeddingModel: string
  graphRerankerModel: string
  graphBuildMode: 'rebuild' | 'incremental'
  graphFreshnessState: string
  graphFreshnessLabel: string
  graphFreshnessHint: string
  graphLoading: boolean
  graphBuildActionLabel: string
  graphBuildMessage: string
  graphBuildProgress: number
  graphBuildSummary: GraphBuildSummary | null
  graphError: string | null
  formatGraphBuildSummary: (summary: GraphBuildSummary | null) => string
  graphFreshnessClass: (state: string) => string
  pipeline: Array<{ key: string; label: string; done: boolean }>
  graphReady: boolean
  hasOasisAnalysis: boolean
  oasisTaskPolling: boolean
  oasisPrepareLoading: boolean
  oasisTask: OasisTask | null
  oasisTaskLastId: string
  graphAnalysisLoading: boolean
  graphAnalysisError: string | null
  oasisPrepareError: string | null
  oasisTaskError: string | null
  graphAnalysisResult: string | null
  oasisPackage: Record<string, any> | null
  oasisRunResult: Record<string, any> | null
  oasisReport: Record<string, any> | null
  graphAnalysisPrompt: string
  oasisAnalysisModel: string
  oasisSimulationModel: string
  oasisReportModel: string
  oasisStageClass: (done: boolean) => string
  oasisTaskStatusColor: (status: string) => string
  graphData: GraphData
  projectId: string
}>()

const emit = defineEmits<{
  'update:ontologyRequirement': [value: string]
  'update:ontologyModel': [value: string]
  'update:graphBuildModel': [value: string]
  'update:graphEmbeddingModel': [value: string]
  'update:graphRerankerModel': [value: string]
  'update:graphBuildMode': [value: 'rebuild' | 'incremental']
  'generate-ontology': []
  'build-graph': []
  'update:graphAnalysisPrompt': [value: string]
  'update:oasisAnalysisModel': [value: string]
  'update:oasisSimulationModel': [value: string]
  'update:oasisReportModel': [value: string]
  analyze: []
  prepare: []
  run: []
  report: []
  'refresh-status': []
  'open-full-graph': []
}>()
</script>

<template>
  <ProjectGraphBuildPanel
    :visible="rightPanelTab === 'graph'"
    :workflow-source-text-length="workflowSourceTextLength"
    :ontology-requirement="ontologyRequirement"
    :models-loading="modelsLoading"
    :models="models"
    :ontology-model="ontologyModel"
    :ontology-loading="ontologyLoading"
    :graph-can-build="graphCanBuild"
    :ontology-message="ontologyMessage"
    :ontology-progress="ontologyProgress"
    :graph-parsing-file="graphParsingFile"
    :ontology-error="ontologyError"
    :ontology-data="ontologyData"
    :has-ontology="hasOntology"
    :ontology-meta="ontologyMeta"
    :graph-build-model="graphBuildModel"
    :embedding-models="embeddingModels"
    :graph-embedding-model="graphEmbeddingModel"
    :graph-reranker-model="graphRerankerModel"
    :graph-build-mode="graphBuildMode"
    :graph-freshness-state="graphFreshnessState"
    :graph-freshness-label="graphFreshnessLabel"
    :graph-freshness-hint="graphFreshnessHint"
    :graph-loading="graphLoading"
    :graph-build-action-label="graphBuildActionLabel"
    :graph-build-message="graphBuildMessage"
    :graph-build-progress="graphBuildProgress"
    :graph-build-summary="graphBuildSummary"
    :graph-error="graphError"
    :format-graph-build-summary="formatGraphBuildSummary"
    :graph-freshness-class="graphFreshnessClass"
    @update:ontology-requirement="emit('update:ontologyRequirement', $event)"
    @update:ontology-model="emit('update:ontologyModel', $event)"
    @update:graph-build-model="emit('update:graphBuildModel', $event)"
    @update:graph-embedding-model="emit('update:graphEmbeddingModel', $event)"
    @update:graph-reranker-model="emit('update:graphRerankerModel', $event)"
    @update:graph-build-mode="emit('update:graphBuildMode', $event)"
    @generate-ontology="emit('generate-ontology')"
    @build-graph="emit('build-graph')"
  />

  <ProjectOasisAnalysisCard
    :visible="rightPanelTab === 'oasis'"
    :pipeline="pipeline"
    :models="models"
    :models-loading="modelsLoading"
    :graph-ready="graphReady"
    :has-oasis-analysis="hasOasisAnalysis"
    :oasis-task-polling="oasisTaskPolling"
    :oasis-prepare-loading="oasisPrepareLoading"
    :oasis-task="oasisTask"
    :oasis-task-last-id="oasisTaskLastId"
    :graph-analysis-loading="graphAnalysisLoading"
    :graph-analysis-error="graphAnalysisError"
    :oasis-prepare-error="oasisPrepareError"
    :oasis-task-error="oasisTaskError"
    :graph-analysis-result="graphAnalysisResult"
    :oasis-package="oasisPackage"
    :oasis-run-result="oasisRunResult"
    :oasis-report="oasisReport"
    :graph-analysis-prompt="graphAnalysisPrompt"
    :oasis-analysis-model="oasisAnalysisModel"
    :oasis-simulation-model="oasisSimulationModel"
    :oasis-report-model="oasisReportModel"
    :oasis-stage-class="oasisStageClass"
    :oasis-task-status-color="oasisTaskStatusColor"
    @update:graph-analysis-prompt="emit('update:graphAnalysisPrompt', $event)"
    @update:oasis-analysis-model="emit('update:oasisAnalysisModel', $event)"
    @update:oasis-simulation-model="emit('update:oasisSimulationModel', $event)"
    @update:oasis-report-model="emit('update:oasisReportModel', $event)"
    @analyze="emit('analyze')"
    @prepare="emit('prepare')"
    @run="emit('run')"
    @report="emit('report')"
    @refresh-status="emit('refresh-status')"
  />

  <div v-if="rightPanelTab === 'graph' && graphData.nodes.length > 0" class="space-y-4">
    <div class="h-72 overflow-hidden rounded-lg">
      <GraphPanel :data="graphData" />
    </div>
    <Button
      variant="ghost"
      size="sm"
      class="w-full"
      @click="emit('open-full-graph')"
    >
      Open Full Graph View
    </Button>
  </div>

  <div v-else-if="rightPanelTab === 'graph' && !graphLoading" class="py-8 text-center">
    <Network class="mx-auto mb-3 h-10 w-10 text-stone-600 dark:text-zinc-500" />
    <p class="text-sm text-stone-500 dark:text-zinc-500">No graph data yet. Follow steps 1-2 to build the graph.</p>
  </div>

  <GraphSearch v-if="rightPanelTab === 'graph'" :project-id="projectId" />
</template>
