<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import AppLayout from '@/components/layout/AppLayout.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import TextEditor from '@/components/editor/TextEditor.vue'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import { runOperation, runOperationWithFile, getModels } from '@/api/projects'
import type { ModelInfo } from '@/api/projects'
import {
  addToGraph,
  analyzeWithOasis,
  generateOntology,
  getOasisTaskStatus,
  getVisualization,
  startPrepareOasisTask,
  startReportOasisTask,
  startRunOasisTask,
} from '@/api/graph'
import type { ComponentModelConfig, Operation, GraphData, OasisTask, ProjectOntology, ProjectOasisAnalysis } from '@/types'
import { extractTextFromDocument, GRAPH_DOCUMENT_ACCEPT } from '@/utils/document'
import {
  Save,
  Sparkles,
  ArrowRight,
  Search,
  RefreshCw,
  FileText,
  Network,
  ChevronLeft,
  Upload,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const toast = useToast()

const projectId = computed(() => route.params.id as string)
const content = ref('')
const saving = ref(false)
const activeTab = ref<'ai' | 'graph'>('ai')
const operationType = ref('CREATE')
const componentModels = ref<ComponentModelConfig>({})
const operationLoading = ref(false)
const operationResult = ref<string | null>(null)
const operationError = ref<string | null>(null)

const graphData = ref<GraphData>({ nodes: [], edges: [] })
const graphLoading = ref(false)
const graphError = ref<string | null>(null)
const graphSourceMode = ref<'editor' | 'documents'>('editor')
const graphFiles = ref<File[]>([])
const graphDragOver = ref(false)
const graphFileInput = ref<HTMLInputElement | null>(null)
const graphBuildProgress = ref(0)
const graphBuildMessage = ref('')
const graphParsingFile = ref<string | null>(null)
const graphInputCacheKey = ref('')
const graphInputCacheText = ref('')

const ontologyLoading = ref(false)
const ontologyError = ref<string | null>(null)
const ontologyData = ref<ProjectOntology | null>(null)
const oasisAnalysisData = ref<ProjectOasisAnalysis | null>(null)
const ontologyProgress = ref(0)
const ontologyMessage = ref('')
const ontologyRequirement = ref('')

const graphAnalysisPrompt = ref('Generate OASIS analysis and continuation guidance based on this graph.')
const graphAnalysisLoading = ref(false)
const graphAnalysisError = ref<string | null>(null)
const graphAnalysisResult = ref<string | null>(null)
const oasisPackage = ref<Record<string, any> | null>(null)
const oasisRunResult = ref<Record<string, any> | null>(null)
const oasisReport = ref<Record<string, any> | null>(null)
const oasisPrepareLoading = ref(false)
const oasisPrepareError = ref<string | null>(null)
const oasisTask = ref<OasisTask | null>(null)
const oasisTaskError = ref<string | null>(null)
const oasisTaskPolling = ref(false)
let oasisTaskTimer: ReturnType<typeof setInterval> | null = null

const selectedFile = ref<File | null>(null)
const dragOver = ref(false)
const models = ref<ModelInfo[]>([])
const modelsLoading = ref(false)

const graphCanBuild = computed(() =>
  graphSourceMode.value === 'editor' ? !!content.value.trim() : graphFiles.value.length > 0
)
const hasOntology = computed(() => !!ontologyData.value && (ontologyData.value.entity_types?.length || 0) > 0)
const hasOasisAnalysis = computed(() => !!oasisAnalysisData.value?.scenario_summary)
const graphReady = computed(
  () => !!projectStore.currentProject?.cognee_dataset_id || graphData.value.nodes.length > 0
)
const oasisPipeline = computed(() => {
  const analysisDone = hasOasisAnalysis.value
  const packageDone = !!oasisPackage.value
  const runDone = !!oasisRunResult.value
  const reportDone = !!oasisReport.value
  return [
    { key: 'analysis', label: 'Analyze', done: analysisDone },
    { key: 'prepare', label: 'Prepare', done: packageDone },
    { key: 'run', label: 'Run', done: runDone },
    { key: 'report', label: 'Report', done: reportDone },
  ]
})

const isFileUploadOperation = computed(() =>
  operationType.value !== 'CREATE'
)

const operationTypes = [
  { value: 'CREATE', label: 'Create', icon: Sparkles, description: 'Start from zero with base info' },
  { value: 'CONTINUE', label: 'Continue', icon: ArrowRight, description: 'Continue based on uploaded document' },
  { value: 'ANALYZE', label: 'Analyze', icon: Search, description: 'Analyze uploaded document' },
  { value: 'REWRITE', label: 'Rewrite', icon: RefreshCw, description: 'Rewrite uploaded document' },
  { value: 'SUMMARIZE', label: 'Summarize', icon: FileText, description: 'Summarize uploaded document' },
]

const operationModelKey = computed(() => `operation_${operationType.value.toLowerCase()}`)

const operationModel = computed({
  get: () => componentModels.value[operationModelKey.value] || '',
  set: (value: string) => setComponentModel(operationModelKey.value, value),
})

const ontologyModel = computed({
  get: () => componentModels.value.ontology_generation || '',
  set: (value: string) => setComponentModel('ontology_generation', value),
})

const oasisAnalysisModel = computed({
  get: () => componentModels.value.oasis_analysis || '',
  set: (value: string) => setComponentModel('oasis_analysis', value),
})

const oasisSimulationModel = computed({
  get: () => componentModels.value.oasis_simulation_config || '',
  set: (value: string) => setComponentModel('oasis_simulation_config', value),
})

const oasisReportModel = computed({
  get: () => componentModels.value.oasis_report || '',
  set: (value: string) => setComponentModel('oasis_report', value),
})

function parseError(e: any, fallback: string): string {
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback
}

function stopOasisTaskPolling() {
  if (oasisTaskTimer) {
    clearInterval(oasisTaskTimer)
    oasisTaskTimer = null
  }
  oasisTaskPolling.value = false
}

async function applyOasisTaskResult(task: OasisTask) {
  const result = task.result || {}
  if (result.package && typeof result.package === 'object') {
    oasisPackage.value = result.package
  }
  if (result.run_result && typeof result.run_result === 'object') {
    oasisRunResult.value = result.run_result
  }
  if (result.report && typeof result.report === 'object') {
    oasisReport.value = result.report
  }
  await loadProject()
}

async function pollOasisTask(taskId: string) {
  try {
    const data = await getOasisTaskStatus(projectId.value, taskId)
    oasisTask.value = data.task
    if (data.task.status === 'completed') {
      stopOasisTaskPolling()
      await applyOasisTaskResult(data.task)
    } else if (data.task.status === 'failed') {
      stopOasisTaskPolling()
      oasisTaskError.value = data.task.error || data.task.message || 'OASIS task failed'
    }
  } catch (e: any) {
    stopOasisTaskPolling()
    oasisTaskError.value = parseError(e, 'Failed to fetch OASIS task status')
  }
}

function startOasisTaskPolling(taskId: string) {
  stopOasisTaskPolling()
  oasisTaskPolling.value = true
  void pollOasisTask(taskId)
  oasisTaskTimer = setInterval(() => {
    void pollOasisTask(taskId)
  }, 2000)
}

function normalizeComponentModels(raw: ComponentModelConfig | null | undefined): ComponentModelConfig {
  if (!raw || typeof raw !== 'object') return {}
  const next: ComponentModelConfig = {}
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value === 'string' && value.trim()) {
      next[key] = value.trim()
    }
  }
  return next
}

async function persistComponentModels() {
  try {
    await projectStore.updateProject(projectId.value, { component_models: componentModels.value })
  } catch {
    // API interceptor handles toast
  }
}

function setComponentModel(key: string, value: string) {
  const normalized = (value || '').trim()
  const next: ComponentModelConfig = { ...componentModels.value }
  if (normalized) {
    next[key] = normalized
  } else {
    delete next[key]
  }
  componentModels.value = next
  void persistComponentModels()
}

function graphInputFingerprint(): string {
  if (graphSourceMode.value === 'editor') {
    return `editor:${content.value}`
  }
  const filesSig = graphFiles.value
    .map((f) => `${f.name}:${f.size}:${f.lastModified}`)
    .sort()
    .join('|')
  return `docs:${filesSig}`
}

async function resolveGraphInputText(forPhase: 'ontology' | 'build'): Promise<string> {
  const key = graphInputFingerprint()
  if (graphInputCacheKey.value === key && graphInputCacheText.value.trim()) {
    return graphInputCacheText.value
  }

  if (graphSourceMode.value === 'editor') {
    const text = content.value.trim()
    if (!text) throw new Error('Editor content is empty')
    graphInputCacheKey.value = key
    graphInputCacheText.value = text
    return text
  }

  if (graphFiles.value.length === 0) {
    throw new Error('Please upload at least one document')
  }

  const chunks: string[] = []
  for (let i = 0; i < graphFiles.value.length; i += 1) {
    const file = graphFiles.value[i]
    graphParsingFile.value = file.name
    const base = forPhase === 'ontology' ? 15 : 20
    const span = forPhase === 'ontology' ? 55 : 45
    if (forPhase === 'ontology') {
      ontologyProgress.value = base + Math.round(((i + 1) / graphFiles.value.length) * span)
      ontologyMessage.value = 'Extracting text from documents...'
    } else {
      graphBuildProgress.value = base + Math.round(((i + 1) / graphFiles.value.length) * span)
      graphBuildMessage.value = 'Extracting text from documents...'
    }
    let text = ''
    try {
      text = await extractTextFromDocument(file)
    } catch (err: any) {
      throw new Error(`${file.name}: ${err?.message || 'Failed to parse document'}`)
    }
    if (text) chunks.push(`\n\n===== ${file.name} =====\n${text}`)
  }

  const merged = chunks.join('\n').trim()
  if (!merged) throw new Error('No readable text was extracted from uploaded files')
  graphInputCacheKey.value = key
  graphInputCacheText.value = merged
  return merged
}

function formatOasisAnalysis(analysis: ProjectOasisAnalysis | null): string {
  if (!analysis) return 'No OASIS analysis output returned.'
  const lines: string[] = []
  if (analysis.scenario_summary) {
    lines.push(`Scenario: ${analysis.scenario_summary}`)
  }
  if (analysis.key_drivers?.length) {
    lines.push('Key Drivers:')
    lines.push(...analysis.key_drivers.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.continuation_guidance?.next_steps?.length) {
    lines.push('Next Steps:')
    lines.push(...analysis.continuation_guidance.next_steps.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.continuation_guidance?.avoid?.length) {
    lines.push('Avoid:')
    lines.push(...analysis.continuation_guidance.avoid.slice(0, 8).map((item) => `- ${item}`))
  }
  if (analysis.simulation_config?.time_config) {
    const t = analysis.simulation_config.time_config
    lines.push('Simulation Time Config:')
    lines.push(`- Total Hours: ${t.total_hours}`)
    lines.push(`- Minutes Per Round: ${t.minutes_per_round}`)
    lines.push(`- Peak Hours: ${(t.peak_hours || []).join(', ') || 'N/A'}`)
  }
  if (analysis.simulation_config?.events?.length) {
    lines.push('Planned Events:')
    lines.push(
      ...analysis.simulation_config.events
        .slice(0, 6)
        .map((event) => `- H+${event.trigger_hour}: ${event.title}${event.description ? ` (${event.description})` : ''}`)
    )
  }
  if (analysis.simulation_config?.agent_activity?.length) {
    lines.push(`Agent Activity Config: ${analysis.simulation_config.agent_activity.length} agents`)
  }
  return lines.join('\n')
}

async function loadProject() {
  await projectStore.fetchProject(projectId.value)
  if (projectStore.currentProject) {
    content.value = projectStore.currentProject.content || ''
    ontologyData.value = projectStore.currentProject.ontology_schema || null
    const savedOasis = projectStore.currentProject.oasis_analysis || null
    oasisAnalysisData.value = savedOasis
    graphAnalysisResult.value = savedOasis ? formatOasisAnalysis(savedOasis) : null
    oasisPackage.value =
      savedOasis && typeof savedOasis.latest_package === 'object' && savedOasis.latest_package
        ? savedOasis.latest_package
        : null
    oasisRunResult.value =
      savedOasis && typeof savedOasis.latest_run === 'object' && savedOasis.latest_run
        ? savedOasis.latest_run
        : null
    oasisReport.value =
      savedOasis && typeof savedOasis.latest_report === 'object' && savedOasis.latest_report
        ? savedOasis.latest_report
        : null
    ontologyRequirement.value = projectStore.currentProject.simulation_requirement || ''
    componentModels.value = normalizeComponentModels(projectStore.currentProject.component_models)
  }
  await projectStore.fetchOperations(projectId.value)
}

async function handleSave() {
  saving.value = true
  try {
    await projectStore.updateProject(projectId.value, { content: content.value })
    toast.success('Project saved')
  } catch {
    // API interceptor handles the error toast
  } finally {
    saving.value = false
  }
}

async function handleOperation() {
  if (operationType.value !== 'CREATE') {
    operationError.value = 'This mode requires document upload.'
    return
  }
  operationLoading.value = true
  operationResult.value = null
  operationError.value = null
  try {
    const result: Operation = await runOperation(projectId.value, {
      type: operationType.value,
      input: content.value,
      model: operationModel.value || undefined,
    })
    operationResult.value = result.output
    if (result.output && (operationType.value === 'CREATE' || operationType.value === 'CONTINUE')) {
      content.value = content.value ? content.value + '\n\n' + result.output : result.output
    }
    toast.success('Operation completed')
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    operationError.value = parseError(e, 'Operation failed')
  } finally {
    operationLoading.value = false
  }
}

async function handleGenerateOntology() {
  if (ontologyLoading.value || !graphCanBuild.value) return
  ontologyLoading.value = true
  ontologyError.value = null
  ontologyProgress.value = 5
  ontologyMessage.value = 'Preparing ontology generation...'
  graphParsingFile.value = null
  try {
    const sourceText = await resolveGraphInputText('ontology')
    ontologyProgress.value = Math.max(ontologyProgress.value, 75)
    ontologyMessage.value = 'Generating ontology...'
    const data = await generateOntology(
      projectId.value,
      sourceText,
      ontologyRequirement.value || undefined,
      ontologyModel.value || undefined
    )
    ontologyData.value = data.ontology
    ontologyProgress.value = 100
    ontologyMessage.value = 'Ontology generated'
    await loadProject()
    toast.success('Ontology generated successfully')
  } catch (e: any) {
    ontologyError.value = parseError(e, 'Failed to generate ontology')
  } finally {
    graphParsingFile.value = null
    ontologyLoading.value = false
  }
}

async function handleBuildGraph() {
  if (graphLoading.value || !graphCanBuild.value) return
  if (!hasOntology.value) {
    graphError.value = 'Please generate ontology before building the graph'
    return
  }
  graphLoading.value = true
  graphError.value = null
  graphBuildProgress.value = 5
  graphBuildMessage.value = 'Preparing graph build...'
  graphParsingFile.value = null
  try {
    const sourceText = await resolveGraphInputText('build')
    graphBuildProgress.value = Math.max(graphBuildProgress.value, 75)
    graphBuildMessage.value = 'Building knowledge graph...'
    await addToGraph(projectId.value, sourceText, ontologyData.value)
    graphBuildProgress.value = 92
    graphBuildMessage.value = 'Loading graph visualization...'
    await loadGraphData()
    await loadProject()
    graphBuildProgress.value = 100
    graphBuildMessage.value = 'Graph build completed'
    toast.success('Knowledge graph built successfully')
  } catch (e: any) {
    graphError.value = parseError(e, 'Failed to build graph')
  } finally {
    graphParsingFile.value = null
    graphLoading.value = false
  }
}

async function handleGraphAnalysis() {
  if (graphAnalysisLoading.value || !graphReady.value) return
  graphAnalysisLoading.value = true
  graphAnalysisError.value = null
  graphAnalysisResult.value = null
  oasisPackage.value = null
  oasisRunResult.value = null
  oasisReport.value = null
  oasisTaskError.value = null
  oasisPrepareError.value = null
  try {
    const sourceText = graphInputCacheText.value.trim()
      ? graphInputCacheText.value
      : content.value.trim()
    const result = await analyzeWithOasis(
      projectId.value,
      {
        text: sourceText || undefined,
        prompt: graphAnalysisPrompt.value.trim() || undefined,
        requirement: ontologyRequirement.value.trim() || undefined,
        analysis_model: oasisAnalysisModel.value || undefined,
        simulation_model: oasisSimulationModel.value || undefined,
      }
    )
    oasisAnalysisData.value = result.analysis
    graphAnalysisResult.value = formatOasisAnalysis(result.analysis)
    await loadProject()
  } catch (e: any) {
    graphAnalysisError.value = parseError(e, 'Graph analysis failed')
  } finally {
    graphAnalysisLoading.value = false
  }
}

async function handlePrepareOasisPackage() {
  if (oasisPrepareLoading.value || !graphReady.value) return
  oasisPrepareLoading.value = true
  oasisPrepareError.value = null
  oasisTaskError.value = null
  try {
    const sourceText = graphInputCacheText.value.trim()
      ? graphInputCacheText.value
      : content.value.trim()
    const result = await startPrepareOasisTask(projectId.value, {
      text: sourceText || undefined,
      prompt: graphAnalysisPrompt.value.trim() || undefined,
      requirement: ontologyRequirement.value.trim() || undefined,
      analysis_model: oasisAnalysisModel.value || undefined,
      simulation_model: oasisSimulationModel.value || undefined,
    })
    oasisTask.value = result.task
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS package task started')
  } catch (e: any) {
    oasisPrepareError.value = parseError(e, 'Failed to prepare OASIS package')
  } finally {
    oasisPrepareLoading.value = false
  }
}

async function handleRunOasisSimulation() {
  if (!graphReady.value || !hasOasisAnalysis.value) return
  oasisTaskError.value = null
  try {
    const result = await startRunOasisTask(projectId.value, {
      package: oasisPackage.value || undefined,
    })
    oasisTask.value = result.task
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS run task started')
  } catch (e: any) {
    oasisTaskError.value = parseError(e, 'Failed to start OASIS run task')
  }
}

async function handleGenerateOasisReport() {
  if (!graphReady.value || !hasOasisAnalysis.value) return
  oasisTaskError.value = null
  try {
    const result = await startReportOasisTask(projectId.value, {
      report_model: oasisReportModel.value || undefined,
    })
    oasisTask.value = result.task
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS report task started')
  } catch (e: any) {
    oasisTaskError.value = parseError(e, 'Failed to start OASIS report task')
  }
}

async function loadGraphData() {
  try {
    graphData.value = await getVisualization(projectId.value)
  } catch {
    graphData.value = { nodes: [], edges: [] }
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusColor(status: string) {
  const colors: Record<string, string> = {
    COMPLETED: 'text-emerald-400',
    FAILED: 'text-red-400',
    PROCESSING: 'text-yellow-400',
    PENDING: 'text-slate-400',
  }
  return colors[status] || 'text-slate-400'
}

function oasisTaskStatusColor(status: string) {
  const colors: Record<string, string> = {
    completed: 'text-emerald-300',
    failed: 'text-red-300',
    processing: 'text-amber-300',
    pending: 'text-slate-300',
  }
  return colors[status] || 'text-slate-300'
}

function oasisStageClass(done: boolean) {
  return done
    ? 'border-emerald-600/60 bg-emerald-900/20 text-emerald-200'
    : 'border-slate-700 bg-slate-800/60 text-slate-400'
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const data = await getModels()
    models.value = data
  } catch {
    models.value = []
  } finally {
    modelsLoading.value = false
  }
}

function handleFileDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) selectedFile.value = file
}

function openGraphFilePicker() {
  graphFileInput.value?.click()
}

function addGraphFiles(fileList: FileList | null) {
  if (!fileList?.length) return
  const incoming = Array.from(fileList)
  const next = [...graphFiles.value]
  for (const file of incoming) {
    const exists = next.some((f) => f.name === file.name && f.size === file.size)
    if (!exists) next.push(file)
  }
  graphFiles.value = next
}

function handleGraphFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  addGraphFiles(input.files)
  input.value = ''
}

function handleGraphFileDrop(e: DragEvent) {
  graphDragOver.value = false
  addGraphFiles(e.dataTransfer?.files || null)
}

function removeGraphFile(index: number) {
  graphFiles.value.splice(index, 1)
}

function clearGraphFiles() {
  graphFiles.value = []
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) selectedFile.value = file
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function handleFileOperation() {
  if (operationType.value === 'CREATE') {
    operationError.value = 'CREATE uses editor base info and does not require upload.'
    return
  }
  if (!selectedFile.value) return
  operationLoading.value = true
  operationResult.value = null
  operationError.value = null
  try {
    const result: Operation = await runOperationWithFile(
      projectId.value,
      selectedFile.value,
      operationType.value,
      operationModel.value || undefined
    )
    operationResult.value = result.output
    if (result.output && operationType.value === 'CONTINUE') {
      content.value = content.value ? `${content.value}\n\n${result.output}` : result.output
    }
    toast.success('Operation completed')
    selectedFile.value = null
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    operationError.value = parseError(e, 'Operation failed')
  } finally {
    operationLoading.value = false
  }
}

onMounted(() => {
  loadProject()
  loadModels()
})

onUnmounted(() => {
  stopOasisTaskPolling()
})

watch(
  [graphSourceMode, content, graphFiles],
  () => {
    graphInputCacheKey.value = ''
    graphInputCacheText.value = ''
  },
  { deep: true }
)

watch(operationType, (type) => {
  operationError.value = null
  operationResult.value = null
  if (type === 'CREATE') {
    selectedFile.value = null
  }
})

watch(
  () => route.params.id,
  () => {
    if (route.params.id) {
      stopOasisTaskPolling()
      graphFiles.value = []
      graphError.value = null
      graphBuildMessage.value = ''
      graphBuildProgress.value = 0
      ontologyError.value = null
      ontologyMessage.value = ''
      ontologyProgress.value = 0
      ontologyData.value = null
      oasisAnalysisData.value = null
      graphAnalysisResult.value = null
      graphAnalysisError.value = null
      oasisPackage.value = null
      oasisRunResult.value = null
      oasisReport.value = null
      oasisPrepareError.value = null
      oasisTask.value = null
      oasisTaskError.value = null
      loadProject()
    }
  }
)

watch(activeTab, (tab) => {
  if (tab === 'graph') loadGraphData()
})
</script>

<template>
  <AppLayout>
    <template #sidebar>
      <AppSidebar :active-id="projectId" />
    </template>

    <div v-if="projectStore.projectLoading" class="flex items-center justify-center h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
    </div>

    <div v-else-if="!projectStore.currentProject" class="flex items-center justify-center h-full">
      <p class="text-slate-500">Project not found</p>
    </div>

    <div v-else class="flex h-full">
      <!-- Left: Editor -->
      <div class="flex-1 flex flex-col border-r border-slate-700/50 min-w-0">
        <div class="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
          <div class="flex items-center gap-3 min-w-0">
            <button
              class="text-slate-400 hover:text-white transition-colors sm:hidden"
              @click="router.push('/dashboard')"
            >
              <ChevronLeft class="w-5 h-5" />
            </button>
            <h1 class="text-lg font-semibold text-white truncate">
              {{ projectStore.currentProject.title }}
            </h1>
          </div>
          <Button variant="secondary" size="sm" :loading="saving" @click="handleSave">
            <Save class="w-4 h-4" />
            Save
          </Button>
        </div>
        <div class="flex-1 p-4 overflow-y-auto">
          <TextEditor v-model="content" placeholder="Start writing your content here..." />
        </div>
      </div>

      <!-- Right: AI / Graph Panel -->
      <div class="w-96 shrink-0 flex flex-col bg-slate-900/50 overflow-hidden">
        <!-- Tabs -->
        <div class="flex border-b border-slate-700/50">
          <button
            class="flex-1 px-4 py-3 text-sm font-medium transition-colors"
            :class="activeTab === 'ai' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-slate-400 hover:text-slate-200'"
            @click="activeTab = 'ai'"
          >
            <span class="flex items-center justify-center gap-1.5">
              <Sparkles class="w-4 h-4" />
              AI Operations
            </span>
          </button>
          <button
            class="flex-1 px-4 py-3 text-sm font-medium transition-colors"
            :class="activeTab === 'graph' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-slate-400 hover:text-slate-200'"
            @click="activeTab = 'graph'"
          >
            <span class="flex items-center justify-center gap-1.5">
              <Network class="w-4 h-4" />
              Knowledge Graph
            </span>
          </button>
        </div>

        <!-- AI Tab -->
        <div v-if="activeTab === 'ai'" class="flex-1 overflow-y-auto p-4 space-y-4">
          <!-- Operation Type -->
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="op in operationTypes"
              :key="op.value"
              class="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors"
              :class="
                operationType === op.value
                  ? 'border-blue-500 bg-blue-600/20 text-blue-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'
              "
              @click="operationType = op.value"
            >
              <component :is="op.icon" class="w-4 h-4" />
              {{ op.label }}
            </button>
          </div>

          <!-- Model Selector -->
          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">Operation Model</label>
            <select
              v-model="operationModel"
              :disabled="modelsLoading"
              class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none disabled:opacity-50"
            >
              <option value="">Use backend default</option>
              <option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </div>

          <!-- File Upload Area (All non-CREATE operations) -->
          <div v-if="isFileUploadOperation" class="space-y-3">
            <div
              class="relative rounded-lg border-2 border-dashed p-6 text-center transition-colors cursor-pointer"
              :class="dragOver ? 'border-blue-500 bg-blue-600/10' : 'border-slate-700 hover:border-slate-500'"
              @dragover.prevent="dragOver = true"
              @dragleave.prevent="dragOver = false"
              @drop.prevent="handleFileDrop"
              @click="($refs.fileInput as HTMLInputElement)?.click()"
            >
              <input
                ref="fileInput"
                type="file"
                accept=".txt,.md,.docx,.pdf"
                class="hidden"
                @change="handleFileSelect"
              />
              <Upload class="w-8 h-8 mx-auto text-slate-500 mb-2" />
              <p class="text-sm text-slate-400">Drop a file here or click to select</p>
              <p class="text-xs text-slate-600 mt-1">.txt, .md, .docx, .pdf</p>
            </div>

            <div v-if="selectedFile" class="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2">
              <div class="flex items-center gap-2 min-w-0">
                <FileText class="w-4 h-4 text-slate-400 shrink-0" />
                <span class="text-sm text-slate-300 truncate">{{ selectedFile.name }}</span>
              </div>
              <span class="text-xs text-slate-500 shrink-0 ml-2">{{ formatFileSize(selectedFile.size) }}</span>
            </div>

            <Button
              variant="primary"
              class="w-full"
              :loading="operationLoading"
              :disabled="!selectedFile || modelsLoading"
              @click="handleFileOperation"
            >
              <Upload class="w-4 h-4" />
              Upload &amp; Run {{ operationTypes.find(o => o.value === operationType)?.label }}
            </Button>
          </div>

          <div
            v-else
            class="rounded-lg border border-blue-700/30 bg-blue-900/10 px-3 py-2 text-xs text-blue-200"
          >
            CREATE mode starts from zero. Please provide your base information in the editor before running.
          </div>

          <!-- Run Button (CREATE only) -->
          <Button
            v-if="!isFileUploadOperation"
            variant="primary"
            class="w-full"
            :loading="operationLoading"
            :disabled="!content.trim() || modelsLoading"
            @click="handleOperation"
          >
            <Sparkles class="w-4 h-4" />
            Run {{ operationTypes.find(o => o.value === operationType)?.label }}
          </Button>

          <!-- Result -->
          <div v-if="operationError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
            {{ operationError }}
          </div>

          <div v-if="operationResult" class="space-y-2">
            <h3 class="text-xs font-medium text-slate-400 uppercase tracking-wider">Result</h3>
            <div class="rounded-lg border border-slate-700/50 bg-slate-800/50 p-3 text-sm text-slate-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
              {{ operationResult }}
            </div>
          </div>

          <!-- Operation History -->
          <div v-if="projectStore.operations.length > 0" class="space-y-2">
            <h3 class="text-xs font-medium text-slate-400 uppercase tracking-wider">History</h3>
            <div class="space-y-1.5 max-h-60 overflow-y-auto">
              <div
                v-for="op in projectStore.operations"
                :key="op.id"
                class="rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2"
              >
                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-slate-300">{{ op.type }}</span>
                  <span :class="statusColor(op.status)" class="text-xs">{{ op.status }}</span>
                </div>
                <div class="flex items-center gap-2 mt-1 text-xs text-slate-500">
                  <span>{{ op.model }}</span>
                  <span>{{ formatDate(op.created_at) }}</span>
                </div>
                <p v-if="op.output" class="text-xs text-slate-400 mt-1 line-clamp-2">{{ op.output }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Graph Tab -->
        <div v-if="activeTab === 'graph'" class="flex-1 overflow-y-auto p-4 space-y-4">
          <Card class="space-y-3">
            <div class="space-y-2">
              <h3 class="text-xs font-medium text-slate-400 uppercase tracking-wider">
                Step 1. Ontology Generation
              </h3>
              <div class="grid grid-cols-2 gap-2">
                <button
                  class="rounded-lg border px-3 py-2 text-sm transition-colors"
                  :class="
                    graphSourceMode === 'editor'
                      ? 'border-blue-500 bg-blue-600/20 text-blue-300'
                      : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                  "
                  @click="graphSourceMode = 'editor'"
                >
                  Editor Content
                </button>
                <button
                  class="rounded-lg border px-3 py-2 text-sm transition-colors"
                  :class="
                    graphSourceMode === 'documents'
                      ? 'border-blue-500 bg-blue-600/20 text-blue-300'
                      : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                  "
                  @click="graphSourceMode = 'documents'"
                >
                  Document Upload
                </button>
              </div>
            </div>

            <div
              v-if="graphSourceMode === 'editor'"
              class="rounded-lg border border-slate-700/60 bg-slate-800/40 p-3"
            >
              <p class="text-sm text-slate-300">
                Generate ontology from current editor content
              </p>
              <p class="mt-1 text-xs text-slate-500">
                {{ content.trim() ? `${content.length} characters detected` : 'Editor content is empty' }}
              </p>
            </div>

            <div v-else class="space-y-2">
              <input
                ref="graphFileInput"
                type="file"
                multiple
                :accept="GRAPH_DOCUMENT_ACCEPT"
                class="hidden"
                @change="handleGraphFileSelect"
              />
              <div
                class="relative rounded-lg border-2 border-dashed p-5 text-center transition-colors cursor-pointer"
                :class="graphDragOver ? 'border-blue-500 bg-blue-600/10' : 'border-slate-700 hover:border-slate-500'"
                @dragover.prevent="graphDragOver = true"
                @dragleave.prevent="graphDragOver = false"
                @drop.prevent="handleGraphFileDrop"
                @click="openGraphFilePicker"
              >
                <Upload class="w-7 h-7 mx-auto text-slate-500 mb-2" />
                <p class="text-sm text-slate-400">Drop documents here or click to select</p>
                <p class="text-xs text-slate-600 mt-1">{{ GRAPH_DOCUMENT_ACCEPT }}</p>
              </div>

              <div
                v-if="graphFiles.length > 0"
                class="rounded-lg border border-slate-700/60 bg-slate-800/40 p-2 max-h-40 overflow-y-auto space-y-1.5"
              >
                <div
                  v-for="(file, idx) in graphFiles"
                  :key="`${file.name}-${file.size}-${idx}`"
                  class="flex items-center justify-between gap-2 rounded bg-slate-800 px-2 py-1.5"
                >
                  <span class="truncate text-xs text-slate-300">{{ file.name }}</span>
                  <div class="flex items-center gap-2 shrink-0">
                    <span class="text-xs text-slate-500">{{ formatFileSize(file.size) }}</span>
                    <button
                      class="text-xs text-slate-500 hover:text-red-400"
                      @click.stop="removeGraphFile(idx)"
                    >
                      Remove
                    </button>
                  </div>
                </div>
                <button
                  class="w-full rounded border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:border-slate-600 hover:text-slate-200 transition-colors"
                  @click="clearGraphFiles"
                >
                  Clear Files
                </button>
              </div>
            </div>

            <div class="space-y-2">
              <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">
                Requirement (optional)
              </label>
              <textarea
                v-model="ontologyRequirement"
                rows="2"
                placeholder="Describe your ontology/simulation focus"
                class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">
                Ontology Model
              </label>
              <select
                v-model="ontologyModel"
                :disabled="modelsLoading"
                class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none disabled:opacity-50"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`ontology-${m.id}`" :value="m.id">{{ m.name }}</option>
              </select>
            </div>

            <Button
              variant="secondary"
              class="w-full"
              :loading="ontologyLoading"
              :disabled="!graphCanBuild"
              @click="handleGenerateOntology"
            >
              <Sparkles class="w-4 h-4" />
              Generate Ontology
            </Button>

            <div v-if="ontologyLoading || ontologyMessage" class="space-y-1">
              <div class="flex items-center justify-between text-xs text-slate-400">
                <span>{{ ontologyMessage || 'Processing...' }}</span>
                <span>{{ ontologyProgress }}%</span>
              </div>
              <div class="h-1.5 rounded bg-slate-800/70 overflow-hidden">
                <div
                  class="h-full bg-blue-500 transition-all duration-300"
                  :style="{ width: `${ontologyProgress}%` }"
                />
              </div>
              <p v-if="graphParsingFile" class="text-xs text-slate-500 truncate">
                Parsing: {{ graphParsingFile }}
              </p>
            </div>

            <div v-if="ontologyError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
              {{ ontologyError }}
            </div>

            <div v-if="hasOntology" class="rounded-lg border border-emerald-700/40 bg-emerald-900/10 p-3 space-y-2">
              <div class="flex items-center justify-between text-xs text-emerald-300">
                <span>Ontology ready</span>
                <span>{{ ontologyData?.entity_types?.length || 0 }} entities / {{ ontologyData?.edge_types?.length || 0 }} relations</span>
              </div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="entity in (ontologyData?.entity_types || []).slice(0, 8)"
                  :key="entity.name"
                  class="rounded-full bg-slate-800/80 px-2 py-0.5 text-xs text-slate-300"
                >
                  {{ entity.name }}
                </span>
              </div>
            </div>
          </Card>

          <Card class="space-y-3">
            <div class="space-y-2">
              <h3 class="text-xs font-medium text-slate-400 uppercase tracking-wider">
                Step 2. Graph Build
              </h3>
              <Button
                variant="primary"
                class="w-full"
                :loading="graphLoading"
                :disabled="!graphCanBuild || !hasOntology"
                @click="handleBuildGraph"
              >
                <Network class="w-4 h-4" />
                Build Knowledge Graph
              </Button>
            </div>

            <div v-if="graphLoading || graphBuildMessage" class="space-y-1">
              <div class="flex items-center justify-between text-xs text-slate-400">
                <span>{{ graphBuildMessage || 'Processing...' }}</span>
                <span>{{ graphBuildProgress }}%</span>
              </div>
              <div class="h-1.5 rounded bg-slate-800/70 overflow-hidden">
                <div
                  class="h-full bg-blue-500 transition-all duration-300"
                  :style="{ width: `${graphBuildProgress}%` }"
                />
              </div>
              <p v-if="graphParsingFile" class="text-xs text-slate-500 truncate">
                Parsing: {{ graphParsingFile }}
              </p>
            </div>

            <p v-if="!hasOntology" class="text-xs text-amber-300">
              Please complete Step 1 first.
            </p>

            <div v-if="graphError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
              {{ graphError }}
            </div>
          </Card>

          <Card class="space-y-3">
            <h3 class="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Step 3. OASIS Analysis
            </h3>
            <div class="grid grid-cols-4 gap-1.5">
              <div
                v-for="phase in oasisPipeline"
                :key="phase.key"
                class="rounded border px-2 py-1 text-center text-[10px] uppercase tracking-wide"
                :class="oasisStageClass(phase.done)"
              >
                {{ phase.label }}
              </div>
            </div>
            <textarea
              v-model="graphAnalysisPrompt"
              rows="2"
              placeholder="Enter OASIS analysis focus"
              class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">
                OASIS Analysis Model
              </label>
              <select
                v-model="oasisAnalysisModel"
                :disabled="modelsLoading"
                class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none disabled:opacity-50"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-analysis-${m.id}`" :value="m.id">{{ m.name }}</option>
              </select>
            </div>
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">
                OASIS Simulation Model
              </label>
              <select
                v-model="oasisSimulationModel"
                :disabled="modelsLoading"
                class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none disabled:opacity-50"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-sim-${m.id}`" :value="m.id">{{ m.name }}</option>
              </select>
            </div>
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400 uppercase tracking-wider">
                OASIS Report Model
              </label>
              <select
                v-model="oasisReportModel"
                :disabled="modelsLoading"
                class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-blue-500 focus:outline-none disabled:opacity-50"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-report-${m.id}`" :value="m.id">{{ m.name }}</option>
              </select>
            </div>
            <Button
              variant="secondary"
              class="w-full"
              :loading="graphAnalysisLoading"
              :disabled="!graphReady"
              @click="handleGraphAnalysis"
            >
              <Search class="w-4 h-4" />
              Run OASIS Analysis
            </Button>
            <Button
              variant="ghost"
              class="w-full"
              :loading="oasisPrepareLoading || (oasisTaskPolling && oasisTask?.task_type === 'oasis_prepare')"
              :disabled="!hasOasisAnalysis || oasisTaskPolling"
              @click="handlePrepareOasisPackage"
            >
              <Sparkles class="w-4 h-4" />
              Prepare OASIS Package (Task)
            </Button>
            <Button
              variant="ghost"
              class="w-full"
              :loading="oasisTaskPolling && oasisTask?.task_type === 'oasis_run'"
              :disabled="!oasisPackage || oasisTaskPolling"
              @click="handleRunOasisSimulation"
            >
              <Network class="w-4 h-4" />
              Run OASIS Simulation (Task)
            </Button>
            <Button
              variant="ghost"
              class="w-full"
              :loading="oasisTaskPolling && oasisTask?.task_type === 'oasis_report'"
              :disabled="!oasisRunResult || oasisTaskPolling"
              @click="handleGenerateOasisReport"
            >
              <FileText class="w-4 h-4" />
              Generate OASIS Report (Task)
            </Button>
            <p v-if="!graphReady" class="text-xs text-amber-300">Build graph before analysis.</p>
            <div v-if="graphAnalysisError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
              {{ graphAnalysisError }}
            </div>
            <div v-if="oasisPrepareError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
              {{ oasisPrepareError }}
            </div>
            <div v-if="oasisTaskError" class="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-300">
              {{ oasisTaskError }}
            </div>
            <div
              v-if="oasisTask"
              class="rounded-lg border border-slate-700/60 bg-slate-800/40 p-3 text-xs text-slate-200 space-y-2"
            >
              <div class="flex items-center justify-between">
                <span class="uppercase tracking-wider text-slate-400">{{ oasisTask.task_type }}</span>
                <span class="capitalize" :class="oasisTaskStatusColor(oasisTask.status)">{{ oasisTask.status }}</span>
              </div>
              <p class="text-slate-300">{{ oasisTask.message || 'Processing...' }}</p>
              <div class="h-1.5 rounded bg-slate-800/70 overflow-hidden">
                <div
                  class="h-full bg-blue-500 transition-all duration-300"
                  :style="{ width: `${oasisTask.progress || 0}%` }"
                />
              </div>
            </div>
            <div
              v-if="graphAnalysisResult"
              class="rounded-lg border border-slate-700/60 bg-slate-800/40 p-3 text-sm text-slate-200 whitespace-pre-wrap max-h-48 overflow-y-auto"
            >
              {{ graphAnalysisResult }}
            </div>
            <div
              v-if="hasOasisAnalysis"
              class="rounded-lg border border-emerald-700/30 bg-emerald-900/10 p-3 text-xs text-emerald-200"
            >
              OASIS summary ready. Guidance and agent profiles are now used by continuation generation.
            </div>
            <div
              v-if="oasisPackage"
              class="rounded-lg border border-blue-700/30 bg-blue-900/10 p-3 text-xs text-blue-200 space-y-1"
            >
              <p>Simulation Package: {{ oasisPackage.simulation_id }}</p>
              <p>Profiles: {{ oasisPackage.profiles?.length || 0 }}</p>
              <p>Events: {{ oasisPackage.simulation_config?.events?.length || 0 }}</p>
              <p>Platforms: {{ (oasisPackage.simulation_config?.active_platforms || []).join(', ') || 'N/A' }}</p>
            </div>
            <div
              v-if="oasisRunResult"
              class="rounded-lg border border-indigo-700/30 bg-indigo-900/10 p-3 text-xs text-indigo-200 space-y-1"
            >
              <p>Run: {{ oasisRunResult.run_id }}</p>
              <p>Rounds: {{ oasisRunResult.metrics?.total_rounds || 0 }}</p>
              <p>Active Agents: {{ oasisRunResult.metrics?.active_agents || 0 }}</p>
              <p>Estimated Posts: {{ oasisRunResult.metrics?.estimated_posts || 0 }}</p>
            </div>
            <div
              v-if="oasisReport"
              class="rounded-lg border border-violet-700/30 bg-violet-900/10 p-3 text-xs text-violet-200 space-y-1"
            >
              <p>Report: {{ oasisReport.report_id }}</p>
              <p class="font-medium">{{ oasisReport.title }}</p>
              <p class="text-violet-300 line-clamp-3">{{ oasisReport.executive_summary }}</p>
            </div>
          </Card>

          <div v-if="graphData.nodes.length > 0" class="space-y-4">
            <div class="h-72 overflow-hidden rounded-lg">
              <GraphPanel :data="graphData" />
            </div>
            <Button
              variant="ghost"
              size="sm"
              class="w-full"
              @click="router.push(`/projects/${projectId}/graph`)"
            >
              Open Full Graph View
            </Button>
          </div>

          <div v-else-if="!graphLoading" class="text-center py-8">
            <Network class="w-10 h-10 mx-auto text-slate-600 mb-3" />
            <p class="text-sm text-slate-500">No graph data yet. Follow steps 1-2 to build the graph.</p>
          </div>

          <GraphSearch :project-id="projectId" />
        </div>
      </div>
    </div>
  </AppLayout>
</template>
