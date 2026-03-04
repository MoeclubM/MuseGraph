<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useToast } from '@/composables/useToast'
import AppLayout from '@/components/layout/AppLayout.vue'
import TextEditor from '@/components/editor/TextEditor.vue'
import GraphPanel from '@/components/graph/GraphPanel.vue'
import GraphSearch from '@/components/graph/GraphSearch.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import Alert from '@/components/ui/Alert.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Select from '@/components/ui/Select.vue'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { runOperation, getEmbeddingModels, getModels, createProjectChapter } from '@/api/projects'
import type { ModelInfo } from '@/api/projects'
import { createSimulation, listSimulations } from '@/api/simulation'
import {
  cancelGraphTask,
  getOasisTaskStatus,
  getVisualization,
  listGraphTasks,
  startAnalyzeOasisTask,
  startBuildGraphTask,
  startGenerateOntologyTask,
  startPrepareOasisTask,
  startReportOasisTask,
  startRunOasisTask,
} from '@/api/graph'
import type {
  ComponentModelConfig,
  Operation,
  GraphData,
  OasisTask,
  ProjectOntology,
  ProjectOasisAnalysis,
  ProjectChapter,
  SimulationRuntime,
} from '@/types'
import { extractTextFromDocument, GRAPH_DOCUMENT_ACCEPT } from '@/utils/document'
import {
  Save,
  Sparkles,
  ArrowRight,
  Search,
  RefreshCw,
  FileText,
  Network,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const toast = useToast()

const projectId = computed(() => route.params.id as string)
const content = ref('')
const activeChapterId = ref<string>('')
const selectedChapterIds = ref<string[]>([])
const chapterTitleDraft = ref('')
const chapterSearchQuery = ref('')
const inlineRenameChapterId = ref('')
const inlineRenameChapterTitle = ref('')
const inlineRenameInputRef = ref<HTMLInputElement | null>(null)
const inlineRenameSubmitting = ref(false)
const projectTitleEditing = ref(false)
const projectTitleDraft = ref('')
const projectTitleSaving = ref(false)
const saving = ref(false)
const operationType = ref('CREATE')
const componentModels = ref<ComponentModelConfig>({})
const operationLoading = ref(false)
const operationResult = ref<string | null>(null)
const operationError = ref<string | null>(null)
const continuationApplyMode = ref<'append' | 'replace' | 'new_chapter'>('new_chapter')
const createUserPrompt = ref('')
const createOutline = ref('')
const createOutlineLoading = ref(false)
const createOutlineError = ref<string | null>(null)
const continueUserInstruction = ref('')
const continueOutline = ref('')
const continueOutlineLoading = ref(false)
const continueOutlineError = ref<string | null>(null)
const confirmedSimulationId = ref('')

const graphData = ref<GraphData>({ nodes: [], edges: [] })
const graphLoading = ref(false)
const graphError = ref<string | null>(null)
const graphBuildProgress = ref(0)
const graphBuildMessage = ref('')
const graphParsingFile = ref<string | null>(null)
const graphInputCacheText = ref('')
const graphBuildMode = ref<'rebuild' | 'incremental'>('rebuild')

const ONTOLOGY_PRESET_PROMPT = `请基于当前章节文本构建可用于 RAG 与剧情推理的本体（Ontology），要求：
1. 实体类型覆盖：人物、组织、地点、事件、时间、物品、关系角色；
2. 关系类型需明确方向与语义，例如：BELONGS_TO、LOCATED_IN、PARTICIPATES_IN、CAUSES、PRECEDES；
3. 避免泛化占位类型（如仅 CONCEPT/RELATED_TO），名称使用清晰的英文大写下划线；
4. 输出实体与关系必须可直接用于图谱入库与后续检索增强生成。`

const ontologyLoading = ref(false)
const ontologyError = ref<string | null>(null)
const ontologyData = ref<ProjectOntology | null>(null)
const oasisAnalysisData = ref<ProjectOasisAnalysis | null>(null)
const ontologyProgress = ref(0)
const ontologyMessage = ref('')
const ontologyRequirement = ref(ONTOLOGY_PRESET_PROMPT)

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
const oasisTaskLastId = ref<string>('')
let oasisTaskTimer: ReturnType<typeof setInterval> | null = null

const pipelineTask = ref<OasisTask | null>(null)
const pipelineTaskError = ref<string | null>(null)
const pipelineTaskPolling = ref(false)
let pipelineTaskTimer: ReturnType<typeof setInterval> | null = null
const taskList = ref<OasisTask[]>([])
const taskListLoading = ref(false)
const taskListError = ref<string | null>(null)
const taskListFilter = ref<'all' | 'running' | 'completed' | 'failed' | 'cancelled'>('all')
const taskCenterExpanded = ref(false)
const cancellingTaskIds = ref<string[]>([])
let taskListTimer: ReturnType<typeof setInterval> | null = null
const TASK_LIST_POLL_MS = 6000
const TASK_DETAIL_POLL_MS = 3000

const models = ref<ModelInfo[]>([])
const embeddingModels = ref<ModelInfo[]>([])
const modelsLoading = ref(false)
const chapterFileInput = ref<HTMLInputElement | null>(null)
const chapterImporting = ref(false)
const chapterImportMessage = ref<string | null>(null)
const chapterContextMenu = ref({
  visible: false,
  chapterId: '',
  x: 0,
  y: 0,
})
const simulationLoading = ref(false)
const simulationCreating = ref(false)
const simulationError = ref<string | null>(null)
const projectSimulations = ref<SimulationRuntime[]>([])
type RightPanelTabKey = 'graph' | 'ai' | 'oasis'
const rightPanelTab = ref<RightPanelTabKey>('graph')
const rightPanelTabs: Array<{ key: RightPanelTabKey; label: string; icon: any }> = [
  { key: 'graph', label: 'Graph + RAG', icon: Network },
  { key: 'ai', label: 'AI Create', icon: Sparkles },
  { key: 'oasis', label: 'OASIS Sim', icon: RefreshCw },
]
const isMobileLayout = ref(false)
const leftPanelCollapsed = ref(false)
const rightPanelCollapsed = ref(false)

const selectedChapters = computed(() => {
  const ids = selectedChapterIds.value.length ? selectedChapterIds.value : (activeChapterId.value ? [activeChapterId.value] : [])
  return ids
    .map((id) => findChapterById(id))
    .filter((chapter): chapter is ProjectChapter => !!chapter)
})

const filteredChapters = computed(() => {
  const keyword = chapterSearchQuery.value.trim().toLowerCase()
  const chapters = projectStore.orderedChapters || []
  if (!keyword) return chapters
  return chapters.filter((chapter) => {
    const title = String(chapter.title || '').toLowerCase()
    const chapterIndex = `chapter ${chapter.order_index + 1}`
    return title.includes(keyword) || chapterIndex.includes(keyword)
  })
})

const workflowSourceText = computed(() => {
  const merged = selectedChapters.value
    .map((chapter) => (chapter.content || '').trim())
    .filter(Boolean)
    .join('\n\n')
    .trim()
  return merged || (content.value || '').trim()
})

const workspaceTextLength = computed(() => {
  const chapters = projectStore.orderedChapters || []
  if (!chapters.length) {
    return (content.value || '').trim().length
  }
  const activeId = activeChapterId.value
  return chapters.reduce((sum, chapter) => {
    const source = chapter.id === activeId ? content.value : (chapter.content || '')
    return sum + source.trim().length
  }, 0)
})
const isWorkspaceEmpty = computed(() => workspaceTextLength.value === 0)
const graphCanBuild = computed(() => !!workflowSourceText.value)
const ontologyMeta = computed(() => ontologyData.value?._meta || null)
const ontologyIsConceptOnly = computed(() => {
  const data = ontologyData.value
  if (!data) return false
  const entities = data.entity_types || []
  const edges = data.edge_types || []
  if (entities.length !== 1 || edges.length !== 1) return false
  return entities[0]?.name === 'CONCEPT' && edges[0]?.name === 'RELATED_TO'
})
const hasOntology = computed(() => {
  const data = ontologyData.value
  if (!data) return false
  const entityCount = data.entity_types?.length || 0
  const edgeCount = data.edge_types?.length || 0
  if (entityCount <= 0 || edgeCount <= 0) return false
  if (ontologyIsConceptOnly.value) return false
  return true
})
const hasOasisAnalysis = computed(() => !!oasisAnalysisData.value?.scenario_summary)
const graphReady = computed(() => !!projectStore.currentProject?.cognee_dataset_id)
const confirmedSimulation = computed(() =>
  projectSimulations.value.find((sim) => sim.simulation_id === confirmedSimulationId.value) || null
)
const createPrerequisitesReady = computed(() =>
  isWorkspaceEmpty.value && !!createUserPrompt.value.trim() && !!createOutline.value.trim()
)
const continuePrerequisitesReady = computed(() =>
  graphReady.value && !!continueUserInstruction.value.trim() && !!continueOutline.value.trim()
)
const runningTaskCount = computed(
  () => taskList.value.filter((task) => isRunningTaskStatus(task.status)).length
)
const filteredTaskList = computed(() => {
  if (taskListFilter.value === 'all') return taskList.value
  if (taskListFilter.value === 'running') {
    return taskList.value.filter((task) => isRunningTaskStatus(task.status))
  }
  if (taskListFilter.value === 'completed') {
    return taskList.value.filter((task) => task.status === 'completed')
  }
  if (taskListFilter.value === 'cancelled') {
    return taskList.value.filter((task) => task.status === 'cancelled')
  }
  return taskList.value.filter((task) => task.status === 'failed')
})
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

const operationPrimaryLabel = computed(() => {
  if (operationType.value === 'CREATE') return '2. Generate Draft From Outline'
  if (operationType.value === 'CONTINUE') return 'Run Continue'
  return `Run ${operationTypes.find((o) => o.value === operationType.value)?.label || operationType.value}`
})

const ontologyModel = computed({
  get: () => componentModels.value.ontology_generation || '',
  set: (value: string) => setComponentModel('ontology_generation', value),
})

const graphBuildModel = computed({
  get: () => componentModels.value.graph_build || componentModels.value.ontology_generation || '',
  set: (value: string) => setComponentModel('graph_build', value),
})

const graphBuildActionLabel = computed(() =>
  graphBuildMode.value === 'incremental'
    ? 'Update Graph Incrementally'
    : 'Build Knowledge Graph (From Zero)'
)

const graphEmbeddingModel = computed({
  get: () => componentModels.value.graph_embedding || '',
  set: (value: string) => setComponentModel('graph_embedding', value),
})

const graphRerankerModel = computed({
  get: () => componentModels.value.graph_reranker || '',
  set: (value: string) => setComponentModel('graph_reranker', value),
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

const contextMenuChapter = computed(() => findChapterById(chapterContextMenu.value.chapterId))
const contextMenuChapterInScope = computed(() => selectedChapterIds.value.includes(chapterContextMenu.value.chapterId))
const chapterContextMenuStyle = computed(() => {
  const width = 188
  const height = 160
  const margin = 8
  const maxX = Math.max(margin, window.innerWidth - width - margin)
  const maxY = Math.max(margin, window.innerHeight - height - margin)
  return {
    left: `${Math.min(Math.max(chapterContextMenu.value.x, margin), maxX)}px`,
    top: `${Math.min(Math.max(chapterContextMenu.value.y, margin), maxY)}px`,
  }
})

function parseError(e: any, fallback: string): string {
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback
}

function beginProjectTitleEdit() {
  if (!projectStore.currentProject) return
  projectTitleDraft.value = projectStore.currentProject.title || ''
  projectTitleEditing.value = true
}

function cancelProjectTitleEdit() {
  projectTitleEditing.value = false
  projectTitleSaving.value = false
  projectTitleDraft.value = projectStore.currentProject?.title || ''
}

async function submitProjectTitleEdit() {
  const project = projectStore.currentProject
  if (!project) return
  const nextTitle = projectTitleDraft.value.trim()
  if (!nextTitle) {
    toast.error('Project name cannot be empty')
    return
  }
  if (nextTitle === (project.title || '').trim()) {
    projectTitleEditing.value = false
    return
  }
  projectTitleSaving.value = true
  try {
    await projectStore.updateProject(projectId.value, { title: nextTitle })
    projectTitleEditing.value = false
    toast.success('Project title updated')
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to update project title'))
  } finally {
    projectTitleSaving.value = false
  }
}

function applyResponsivePanelPreference(force = false) {
  const mobile = window.innerWidth < 1024
  const layoutChanged = mobile !== isMobileLayout.value
  isMobileLayout.value = mobile
  if (force || layoutChanged) {
    leftPanelCollapsed.value = mobile
    rightPanelCollapsed.value = mobile
  }
}

function handleWindowResize() {
  applyResponsivePanelPreference()
}

function isPageVisible(): boolean {
  if (typeof document === 'undefined') return true
  return document.visibilityState === 'visible'
}

function handleVisibilityChange() {
  if (!isPageVisible()) return
  void loadTaskList(true)
  if (pipelineTaskPolling.value && pipelineTask.value?.task_id) {
    void pollPipelineTask(pipelineTask.value.task_id)
  }
  if (oasisTaskPolling.value && oasisTask.value?.task_id) {
    void pollOasisTask(oasisTask.value.task_id)
  }
}

function toggleLeftPanel() {
  const next = !leftPanelCollapsed.value
  leftPanelCollapsed.value = next
  if (isMobileLayout.value && !next) {
    rightPanelCollapsed.value = true
  }
}

function toggleRightPanel() {
  const next = !rightPanelCollapsed.value
  rightPanelCollapsed.value = next
  if (isMobileLayout.value && !next) {
    leftPanelCollapsed.value = true
  }
}

function sortTasksByCreated(tasks: OasisTask[]): OasisTask[] {
  return [...tasks].sort((a, b) => {
    const at = Date.parse(a.created_at || '') || 0
    const bt = Date.parse(b.created_at || '') || 0
    return bt - at
  })
}

function upsertTaskListItem(task: OasisTask) {
  const normalizedTaskId = String(task.task_id || '')
  if (!normalizedTaskId) return
  const next = [...taskList.value]
  const existingIndex = next.findIndex((item) => item.task_id === normalizedTaskId)
  if (existingIndex >= 0) {
    next[existingIndex] = task
  } else {
    next.push(task)
  }
  taskList.value = sortTasksByCreated(next)
}

function replaceTaskList(tasks: OasisTask[]) {
  taskList.value = sortTasksByCreated(tasks)
}

async function loadTaskList(silent = false) {
  if (!silent) {
    taskListLoading.value = true
    taskListError.value = null
  }
  try {
    const response = await listGraphTasks(projectId.value, { limit: 100 })
    const tasks = Array.isArray(response.tasks) ? response.tasks : []
    replaceTaskList(tasks)
  } catch (e: any) {
    if (!silent) {
      taskListError.value = parseError(e, 'Failed to load task list')
    }
  } finally {
    if (!silent) {
      taskListLoading.value = false
    }
  }
}

function stopTaskListPolling() {
  if (taskListTimer) {
    clearInterval(taskListTimer)
    taskListTimer = null
  }
}

function startTaskListPolling() {
  stopTaskListPolling()
  taskListTimer = setInterval(() => {
    if (!isPageVisible()) return
    void loadTaskList(true)
  }, TASK_LIST_POLL_MS)
}

async function handleRefreshTaskList() {
  await loadTaskList()
}

function taskTypeLabel(taskType: string): string {
  const labels: Record<string, string> = {
    ontology_generate: 'Ontology',
    graph_build: 'Graph Build',
    oasis_analyze: 'OASIS Analyze',
    oasis_prepare: 'OASIS Prepare',
    oasis_run: 'OASIS Run',
    oasis_report: 'OASIS Report',
  }
  return labels[taskType] || taskType
}

function taskStatusClass(status: string): string {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'completed') return 'text-emerald-700 dark:text-emerald-300'
  if (normalized === 'failed') return 'text-red-700 dark:text-red-300'
  if (normalized === 'cancelled') return 'text-stone-600 dark:text-zinc-400'
  if (normalized === 'processing') return 'text-amber-700 dark:text-amber-300'
  return 'text-stone-700 dark:text-zinc-300'
}

function isRunningTaskStatus(status: string): boolean {
  const normalized = String(status || '').toLowerCase()
  return normalized === 'pending' || normalized === 'processing'
}

function isTaskCancellable(task: OasisTask): boolean {
  return isRunningTaskStatus(task.status)
}

function isTaskCancelling(taskId: string): boolean {
  return cancellingTaskIds.value.includes(taskId)
}

function syncCancelledTask(task: OasisTask) {
  if (pipelineTask.value?.task_id === task.task_id) {
    pipelineTask.value = task
    stopPipelineTaskPolling()
    ontologyLoading.value = false
    graphLoading.value = false
    if (task.task_type === 'ontology_generate') {
      ontologyMessage.value = task.message || 'Ontology task cancelled'
    } else if (task.task_type === 'graph_build') {
      graphBuildMessage.value = task.message || 'Graph build task cancelled'
    }
  }
  if (oasisTask.value?.task_id === task.task_id) {
    oasisTask.value = task
    stopOasisTaskPolling()
    graphAnalysisLoading.value = false
    oasisPrepareLoading.value = false
  }
}

async function handleCancelTask(task: OasisTask) {
  if (!task?.task_id || !isTaskCancellable(task) || isTaskCancelling(task.task_id)) return
  cancellingTaskIds.value = [...cancellingTaskIds.value, task.task_id]
  try {
    const response = await cancelGraphTask(projectId.value, task.task_id)
    const latest = response.task
    upsertTaskListItem(latest)
    syncPipelineProgress(latest)
    if (latest.status === 'cancelled') {
      syncCancelledTask(latest)
      toast.success(`${taskTypeLabel(latest.task_type)} task cancelled`)
    } else {
      toast.success(`${taskTypeLabel(latest.task_type)} task is already ${latest.status}`)
    }
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to cancel task'))
  } finally {
    cancellingTaskIds.value = cancellingTaskIds.value.filter((id) => id !== task.task_id)
  }
}

function stopPipelineTaskPolling() {
  if (pipelineTaskTimer) {
    clearInterval(pipelineTaskTimer)
    pipelineTaskTimer = null
  }
  pipelineTaskPolling.value = false
}

function syncPipelineProgress(task: OasisTask) {
  if (task.task_type === 'ontology_generate') {
    ontologyLoading.value = isRunningTaskStatus(task.status)
    ontologyProgress.value = Math.max(0, Math.min(100, Number(task.progress || 0)))
    ontologyMessage.value = task.message || 'Generating ontology...'
  } else if (task.task_type === 'graph_build') {
    graphLoading.value = isRunningTaskStatus(task.status)
    graphBuildProgress.value = Math.max(0, Math.min(100, Number(task.progress || 0)))
    graphBuildMessage.value = task.message || 'Building knowledge graph...'
  }
}

async function applyPipelineTaskResult(task: OasisTask) {
  const result = task.result || {}
  if (task.task_type === 'ontology_generate' && result.ontology && typeof result.ontology === 'object') {
    ontologyData.value = result.ontology as ProjectOntology
    ontologyProgress.value = 100
    ontologyMessage.value = task.message || 'Ontology generated'
    ontologyError.value = null
    await loadProject()
  } else if (task.task_type === 'graph_build') {
    graphBuildProgress.value = 100
    graphBuildMessage.value = task.message || 'Knowledge graph built'
    graphError.value = null
    await loadGraphData()
    await loadProject()
  }
}

async function pollPipelineTask(taskId: string) {
  try {
    const data = await getOasisTaskStatus(projectId.value, taskId)
    pipelineTask.value = data.task
    upsertTaskListItem(data.task)
    syncPipelineProgress(data.task)
    if (data.task.task_type === 'graph_build' && isRunningTaskStatus(data.task.status)) {
      await loadGraphData({ preserveOnError: true })
    }
    if (data.task.status === 'completed') {
      stopPipelineTaskPolling()
      await applyPipelineTaskResult(data.task)
    } else if (data.task.status === 'cancelled') {
      syncCancelledTask(data.task)
    } else if (data.task.status === 'failed') {
      stopPipelineTaskPolling()
      if (data.task.task_type === 'ontology_generate') {
        ontologyLoading.value = false
        ontologyError.value = data.task.error || data.task.message || 'Ontology task failed'
      } else if (data.task.task_type === 'graph_build') {
        graphLoading.value = false
        graphError.value = data.task.error || data.task.message || 'Graph build task failed'
      }
      pipelineTaskError.value = data.task.error || data.task.message || 'Task failed'
    }
  } catch (e: any) {
    const wasOntologyLoading = ontologyLoading.value
    const wasGraphLoading = graphLoading.value
    stopPipelineTaskPolling()
    ontologyLoading.value = false
    graphLoading.value = false
    const message = parseError(e, 'Failed to fetch pipeline task status')
    pipelineTaskError.value = message
    const taskType = pipelineTask.value?.task_type || ''
    if (taskType === 'ontology_generate' || wasOntologyLoading) {
      ontologyError.value = message
    }
    if (taskType === 'graph_build' || wasGraphLoading) {
      graphError.value = message
    }
  }
}

function startPipelineTaskPolling(taskId: string) {
  stopPipelineTaskPolling()
  pipelineTaskPolling.value = true
  void pollPipelineTask(taskId)
  pipelineTaskTimer = setInterval(() => {
    if (!isPageVisible()) return
    void pollPipelineTask(taskId)
  }, TASK_DETAIL_POLL_MS)
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
  if (result.analysis && typeof result.analysis === 'object') {
    oasisAnalysisData.value = result.analysis as ProjectOasisAnalysis
    graphAnalysisResult.value = formatOasisAnalysis(result.analysis as ProjectOasisAnalysis)
    graphAnalysisError.value = null
  }
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
    oasisTaskLastId.value = data.task.task_id
    if (data.task.task_type === 'oasis_analyze') {
      graphAnalysisLoading.value = isRunningTaskStatus(data.task.status)
    }
    upsertTaskListItem(data.task)
    if (data.task.status === 'completed') {
      stopOasisTaskPolling()
      if (data.task.task_type === 'oasis_analyze') {
        graphAnalysisLoading.value = false
      }
      await applyOasisTaskResult(data.task)
    } else if (data.task.status === 'cancelled') {
      syncCancelledTask(data.task)
    } else if (data.task.status === 'failed') {
      stopOasisTaskPolling()
      if (data.task.task_type === 'oasis_analyze') {
        graphAnalysisLoading.value = false
        graphAnalysisError.value = data.task.error || data.task.message || 'OASIS analysis task failed'
      }
      oasisTaskError.value = data.task.error || data.task.message || 'OASIS task failed'
    }
  } catch (e: any) {
    stopOasisTaskPolling()
    graphAnalysisLoading.value = false
    oasisTaskError.value = parseError(e, 'Failed to fetch OASIS task status')
  }
}

function startOasisTaskPolling(taskId: string) {
  stopOasisTaskPolling()
  oasisTaskLastId.value = taskId
  oasisTaskPolling.value = true
  void pollOasisTask(taskId)
  oasisTaskTimer = setInterval(() => {
    if (!isPageVisible()) return
    void pollOasisTask(taskId)
  }, TASK_DETAIL_POLL_MS)
}

async function handleRefreshOasisTaskStatus() {
  const taskId = oasisTask.value?.task_id || oasisTaskLastId.value
  if (!taskId) {
    oasisTaskError.value = 'No OASIS task id available to refresh'
    return
  }
  oasisTaskError.value = null
  await pollOasisTask(taskId)
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

async function resolveGraphInputText(forPhase: 'ontology' | 'build'): Promise<string> {
  const text = workflowSourceText.value
  if (!text) {
    throw new Error(
      forPhase === 'ontology'
        ? 'No chapter text available for ontology generation'
        : 'No chapter text available for graph build'
    )
  }
  graphInputCacheText.value = text
  return text
}

async function resolveWorkflowRequestText(forPhase: 'ontology' | 'build'): Promise<string> {
  const scope = chapterScopePayload()
  if (scope.chapter_ids && scope.chapter_ids.length > 0) {
    // For chapter-scoped runs, let backend merge persisted chapter content.
    graphInputCacheText.value = workflowSourceText.value
    return ''
  }
  return resolveGraphInputText(forPhase)
}

function findChapterById(chapterId: string): ProjectChapter | null {
  return (projectStore.orderedChapters || []).find((chapter) => chapter.id === chapterId) || null
}

function syncActiveChapterContentFromState() {
  const chapter = findChapterById(activeChapterId.value)
  if (chapter) {
    content.value = chapter.content || ''
    chapterTitleDraft.value = chapter.title || ''
    return
  }
  content.value = ''
  chapterTitleDraft.value = ''
}

function hasUnsavedDraftChanges(): boolean {
  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) return false
  return (content.value || '') !== (chapter.content || '')
}

function buildContinuationChapterTitle(nextOrder: number): string {
  const heading = continueOutline.value
    .split('\n')
    .map((line) => line.trim())
    .find((line) => !!line)
    || continueUserInstruction.value
      .split('\n')
      .map((line) => line.trim())
      .find((line) => !!line)
    || ''
  const cleaned = heading
    .replace(/^[-*#\d.\)\s]+/, '')
    .replace(/^chapter\s*\d+\s*[:：-]?\s*/i, '')
    .trim()
  const title = cleaned.slice(0, 80)
  return title || `Chapter ${nextOrder + 1}`
}

async function applyCreateOutput(output: string): Promise<string[]> {
  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) {
    content.value = output
    return []
  }
  const title = chapterTitleDraft.value.trim() || chapter.title || `Chapter ${chapter.order_index + 1}`
  await projectStore.updateChapter(projectId.value, chapter.id, {
    title,
    content: output,
  })
  if (!selectedChapterIds.value.includes(chapter.id)) {
    selectedChapterIds.value = [...selectedChapterIds.value, chapter.id]
  }
  syncActiveChapterContentFromState()
  return [chapter.id]
}

async function applyContinuationOutput(output: string): Promise<string[]> {
  if (continuationApplyMode.value === 'new_chapter') {
    const nextOrder = projectStore.orderedChapters.length
    const created = await projectStore.createChapter(projectId.value, {
      title: buildContinuationChapterTitle(nextOrder),
      content: output,
      order_index: nextOrder,
    })
    const newest = created[created.length - 1]
    if (newest) {
      activeChapterId.value = newest.id
      selectedChapterIds.value = [newest.id]
      syncActiveChapterContentFromState()
      return [newest.id]
    }
    return []
  }

  const chapter = findChapterById(activeChapterId.value)
  if (!chapter) {
    content.value = continuationApplyMode.value === 'replace'
      ? output
      : (content.value ? `${content.value}\n\n${output}` : output)
    return []
  }

  const currentContent = chapter.content || ''
  const mergedContent = continuationApplyMode.value === 'replace'
    ? output
    : (currentContent ? `${currentContent}\n\n${output}` : output)
  const title = chapterTitleDraft.value.trim() || chapter.title || `Chapter ${chapter.order_index + 1}`
  await projectStore.updateChapter(projectId.value, chapter.id, {
    title,
    content: mergedContent,
  })
  if (!selectedChapterIds.value.includes(chapter.id)) {
    selectedChapterIds.value = [...selectedChapterIds.value, chapter.id]
  }
  syncActiveChapterContentFromState()
  return [chapter.id]
}

function chapterScopePayload(): { chapter_ids?: string[] } {
  return selectedChapterIds.value.length ? { chapter_ids: selectedChapterIds.value } : {}
}

async function ensureChapterStateInitialized() {
  if (!projectStore.currentProject) return
  const chapters = projectStore.orderedChapters
  if (!chapters.length) {
    await projectStore.fetchChapters(projectId.value)
  }

  const ordered = projectStore.orderedChapters
  if (!ordered.length) {
    activeChapterId.value = ''
    selectedChapterIds.value = []
    content.value = ''
    return
  }

  if (!activeChapterId.value || !findChapterById(activeChapterId.value)) {
    activeChapterId.value = ordered[0].id
  }

  if (!selectedChapterIds.value.length) {
    // Default graph/ontology pipeline scope is the whole project chapters.
    selectedChapterIds.value = ordered.map((chapter) => chapter.id)
  } else {
    selectedChapterIds.value = selectedChapterIds.value.filter((id) => !!findChapterById(id))
    if (!selectedChapterIds.value.length) {
      selectedChapterIds.value = ordered.map((chapter) => chapter.id)
    }
  }

  syncActiveChapterContentFromState()
}

async function handleSelectChapter(chapterId: string) {
  if (chapterId === activeChapterId.value) return
  if (hasUnsavedDraftChanges()) {
    const shouldSwitch = window.confirm('You have unsaved changes in the current chapter. Switch chapter and discard local draft changes?')
    if (!shouldSwitch) return
  }
  activeChapterId.value = chapterId
  if (!selectedChapterIds.value.includes(chapterId)) {
    selectedChapterIds.value = [chapterId, ...selectedChapterIds.value]
  }
  syncActiveChapterContentFromState()
}

function openChapterContextMenu(event: MouseEvent, chapterId: string) {
  chapterContextMenu.value = {
    visible: true,
    chapterId,
    x: event.clientX,
    y: event.clientY,
  }
}

function closeChapterContextMenu() {
  chapterContextMenu.value.visible = false
}

function handleGlobalPointerDown(event: PointerEvent) {
  if (!chapterContextMenu.value.visible) return
  const target = event.target as HTMLElement | null
  if (target?.closest?.('[data-chapter-context-menu="true"]')) return
  closeChapterContextMenu()
}

function handleGlobalKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && inlineRenameChapterId.value) {
    cancelInlineRenameChapter()
    return
  }
  if (event.key === 'Escape') {
    closeChapterContextMenu()
  }
}

function toggleChapterForWorkflow(chapterId: string) {
  if (selectedChapterIds.value.includes(chapterId)) {
    if (selectedChapterIds.value.length === 1) return
    selectedChapterIds.value = selectedChapterIds.value.filter((id) => id !== chapterId)
    if (!selectedChapterIds.value.includes(activeChapterId.value)) {
      activeChapterId.value = selectedChapterIds.value[0] || activeChapterId.value
      syncActiveChapterContentFromState()
    }
    return
  }
  selectedChapterIds.value = [...selectedChapterIds.value, chapterId]
}

function isInlineRenamingChapter(chapterId: string): boolean {
  return inlineRenameChapterId.value === chapterId
}

async function beginInlineRenameChapter(chapterId: string) {
  const chapter = findChapterById(chapterId)
  if (!chapter) return
  inlineRenameChapterId.value = chapterId
  inlineRenameChapterTitle.value = chapter.title || `Chapter ${chapter.order_index + 1}`
  await nextTick()
  inlineRenameInputRef.value?.focus()
  inlineRenameInputRef.value?.select()
}

function cancelInlineRenameChapter() {
  inlineRenameChapterId.value = ''
  inlineRenameChapterTitle.value = ''
}

async function submitInlineRenameChapter() {
  if (inlineRenameSubmitting.value) return
  const chapterId = inlineRenameChapterId.value
  if (!chapterId) return
  const chapter = findChapterById(chapterId)
  if (!chapter) {
    cancelInlineRenameChapter()
    return
  }
  const fallbackTitle = chapter.title || `Chapter ${chapter.order_index + 1}`
  const title = inlineRenameChapterTitle.value.trim() || fallbackTitle
  if (title === fallbackTitle) {
    cancelInlineRenameChapter()
    return
  }
  inlineRenameSubmitting.value = true
  try {
    await projectStore.updateChapter(projectId.value, chapter.id, { title })
    if (activeChapterId.value === chapterId) {
      chapterTitleDraft.value = title
    }
    cancelInlineRenameChapter()
  } finally {
    inlineRenameSubmitting.value = false
  }
}

async function deleteChapterById(chapterId: string) {
  const chapter = findChapterById(chapterId)
  if (!chapter) return
  if (projectStore.orderedChapters.length <= 1) {
    toast.error('At least one chapter must remain')
    return
  }
  const chapterName = chapter.title || `Chapter ${chapter.order_index + 1}`
  if (!window.confirm(`Delete "${chapterName}"?`)) return

  await projectStore.deleteChapter(projectId.value, chapterId)
  if (inlineRenameChapterId.value === chapterId) {
    cancelInlineRenameChapter()
  }
  const remaining = projectStore.orderedChapters
  if (!remaining.length) {
    activeChapterId.value = ''
    selectedChapterIds.value = []
    content.value = ''
    return
  }

  if (!findChapterById(activeChapterId.value)) {
    activeChapterId.value = remaining[0].id
  }
  selectedChapterIds.value = selectedChapterIds.value.filter((id) => id !== chapterId)
  if (!selectedChapterIds.value.length) {
    selectedChapterIds.value = [activeChapterId.value]
  }
  syncActiveChapterContentFromState()
}

async function handleContextMenuOpen() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await handleSelectChapter(chapter.id)
}

async function handleContextMenuRename() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await beginInlineRenameChapter(chapter.id)
}

function handleContextMenuToggleScope() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  toggleChapterForWorkflow(chapter.id)
}

async function handleContextMenuDelete() {
  const chapter = contextMenuChapter.value
  if (!chapter) return
  closeChapterContextMenu()
  await deleteChapterById(chapter.id)
}

async function handleCreateChapter() {
  const nextOrder = projectStore.orderedChapters.length
  await projectStore.createChapter(projectId.value, {
    title: `Chapter ${nextOrder + 1}`,
    content: '',
    order_index: nextOrder,
  })
  const newest = projectStore.orderedChapters[projectStore.orderedChapters.length - 1]
  if (newest) {
    activeChapterId.value = newest.id
    if (!selectedChapterIds.value.includes(newest.id)) {
      selectedChapterIds.value = [...selectedChapterIds.value, newest.id]
    }
    syncActiveChapterContentFromState()
  }
}

function normalizeChapterTitleFromFile(fileName: string): string {
  const trimmed = (fileName || '').trim()
  if (!trimmed) return 'Untitled chapter'
  const dot = trimmed.lastIndexOf('.')
  const base = dot > 0 ? trimmed.slice(0, dot) : trimmed
  return base.trim() || 'Untitled chapter'
}

function openChapterFilePicker() {
  chapterFileInput.value?.click()
}

async function handleChapterFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length || chapterImporting.value) return

  chapterImporting.value = true
  chapterImportMessage.value = null
  let orderIndex = projectStore.orderedChapters.length
  let successCount = 0
  const failedFiles: string[] = []

  try {
    for (let i = 0; i < files.length; i += 1) {
      const file = files[i]
      chapterImportMessage.value = `Importing (${i + 1}/${files.length}): ${file.name}`
      try {
        const text = await extractTextFromDocument(file)
        await createProjectChapter(projectId.value, {
          title: normalizeChapterTitleFromFile(file.name),
          content: (text || '').trim(),
          order_index: orderIndex,
        })
        orderIndex += 1
        successCount += 1
      } catch {
        failedFiles.push(file.name)
      }
    }

    await projectStore.fetchProject(projectId.value)
    await projectStore.fetchChapters(projectId.value)
    await ensureChapterStateInitialized()

    if (successCount > 0) {
      toast.success(`Imported ${successCount} file(s) as chapters`)
    }
    if (failedFiles.length > 0) {
      toast.error(`Failed to import: ${failedFiles.join(', ')}`)
    }
  } finally {
    chapterImporting.value = false
    chapterImportMessage.value = null
  }
}

async function handleDeleteActiveChapter() {
  if (!activeChapterId.value) return
  await deleteChapterById(activeChapterId.value)
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

async function loadProjectSimulations() {
  simulationLoading.value = true
  simulationError.value = null
  try {
    projectSimulations.value = await listSimulations(projectId.value)
  } catch (e: any) {
    simulationError.value = parseError(e, 'Failed to load workflow simulations')
    projectSimulations.value = []
  } finally {
    simulationLoading.value = false
  }
}

async function handleCreateWorkflowSimulation() {
  const project = projectStore.currentProject
  if (!project || !project.cognee_dataset_id) {
    simulationError.value = 'Please build knowledge graph before creating simulation'
    return
  }
  simulationCreating.value = true
  simulationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const result = await createSimulation({
      project_id: project.id,
      graph_id: project.cognee_dataset_id,
      enable_twitter: true,
      enable_reddit: true,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
    })
    await loadProjectSimulations()
    confirmedSimulationId.value = ''
    toast.success('Simulation created')
    await router.push(`/simulation/${result.simulation_id}`)
  } catch (e: any) {
    simulationError.value = parseError(e, 'Failed to create simulation')
  } finally {
    simulationCreating.value = false
  }
}

async function loadProject() {
  await projectStore.fetchProject(projectId.value)
  if (projectStore.currentProject) {
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
    ontologyRequirement.value = projectStore.currentProject.simulation_requirement || ONTOLOGY_PRESET_PROMPT
    componentModels.value = normalizeComponentModels(projectStore.currentProject.component_models)
    projectTitleDraft.value = projectStore.currentProject.title || ''
  }
  await ensureChapterStateInitialized()
  await projectStore.fetchOperations(projectId.value)
  await loadProjectSimulations()
  if (projectStore.currentProject?.cognee_dataset_id) {
    await loadGraphData()
  } else {
    graphData.value = { nodes: [], edges: [] }
  }
  await resumeProjectTasks()
}

async function resumeProjectTasks() {
  try {
    const response = await listGraphTasks(projectId.value, { limit: 60 })
    const tasks = Array.isArray(response.tasks) ? response.tasks : []
    replaceTaskList(tasks)
    taskListError.value = null
    if (!tasks.length) return

    const running = (task: OasisTask) => isRunningTaskStatus(task.status)
    const pipelineRunning = tasks.find((task) =>
      running(task) && (task.task_type === 'ontology_generate' || task.task_type === 'graph_build')
    )
    if (pipelineRunning) {
      syncPipelineProgress(pipelineRunning)
      taskCenterExpanded.value = true
      startPipelineTaskPolling(pipelineRunning.task_id)
    }

    const oasisRunning = tasks.find((task) =>
      running(task)
      && (
        task.task_type === 'oasis_analyze'
        || task.task_type === 'oasis_prepare'
        || task.task_type === 'oasis_run'
        || task.task_type === 'oasis_report'
      )
    )
    if (oasisRunning) {
      taskCenterExpanded.value = true
      startOasisTaskPolling(oasisRunning.task_id)
    } else {
      const latestOasis = tasks.find((task) =>
        task.task_type === 'oasis_analyze'
        || task.task_type === 'oasis_prepare'
        || task.task_type === 'oasis_run'
        || task.task_type === 'oasis_report'
      )
      if (latestOasis) {
        oasisTaskLastId.value = latestOasis.task_id
      }
    }
  } catch (e: any) {
    taskListError.value = parseError(e, 'Failed to load task list')
  }
}

async function handleSave() {
  saving.value = true
  try {
    await persistActiveChapterDraftIfNeeded()
    await ensureChapterStateInitialized()
    toast.success('Project saved')
  } catch {
    // API interceptor handles the error toast
  } finally {
    saving.value = false
  }
}

async function persistActiveChapterDraftIfNeeded() {
  const activeChapter = findChapterById(activeChapterId.value)
  if (!activeChapter) return
  const nextTitle = chapterTitleDraft.value.trim() || activeChapter.title || 'Untitled chapter'
  const nextContent = content.value
  const currentTitle = activeChapter.title || ''
  const currentContent = activeChapter.content || ''
  if (nextTitle === currentTitle && nextContent === currentContent) {
    return
  }
  await projectStore.updateChapter(projectId.value, activeChapter.id, {
    title: nextTitle,
    content: nextContent,
  })
  chapterTitleDraft.value = nextTitle
}

function normalizeChapterIds(chapterIds: string[]): string[] {
  const seen = new Set<string>()
  const normalized: string[] = []
  for (const raw of chapterIds) {
    const id = String(raw || '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    normalized.push(id)
  }
  return normalized
}

async function triggerIncrementalGraphRefresh(chapterIds: string[] = []) {
  if (!hasOntology.value) return
  if (graphLoading.value) return
  const normalized = normalizeChapterIds(chapterIds)
  try {
    const response = await startBuildGraphTask(projectId.value, {
      chapter_ids: normalized.length ? normalized : undefined,
      build_mode: 'incremental',
    })
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success('RAG graph refresh started (incremental)')
  } catch (e: any) {
    toast.error(parseError(e, 'Failed to refresh graph incrementally'))
  }
}

async function handleOperation() {
  const op = operationType.value
  if (op !== 'CREATE' && !graphReady.value) {
    operationError.value = 'Knowledge graph is required for this operation. Please build graph first.'
    return
  }
  operationLoading.value = true
  operationResult.value = null
  operationError.value = null
  try {
    if (op === 'CREATE') {
      if (!isWorkspaceEmpty.value) {
        operationError.value = 'CREATE is only available when workspace text length is 0.'
        return
      }
      if (!createUserPrompt.value.trim()) {
        operationError.value = 'Please provide a creation prompt before CREATE.'
        return
      }
      if (!createOutline.value.trim()) {
        operationError.value = 'Please generate and confirm outline before CREATE.'
        return
      }
    }
    await persistActiveChapterDraftIfNeeded()
    if (op === 'CONTINUE') {
      if (!continueUserInstruction.value.trim()) {
        operationError.value = 'Please provide continuation instruction before CONTINUE.'
        return
      }
      if (!continueOutline.value.trim()) {
        operationError.value = 'Please generate continuation outline before CONTINUE.'
        return
      }
    }
    const input =
      op === 'CREATE'
        ? [
            'Generate a full draft strictly based on the outline below.',
            'Stay faithful to the user prompt and keep narrative consistency.',
            '',
            '[User Prompt]',
            createUserPrompt.value.trim(),
            '',
            '[Outline]',
            createOutline.value.trim(),
          ].join('\n')
        : op === 'CONTINUE'
          ? [
              'Continue writing according to the continuation outline and user instruction.',
              'Use graph retrieval context (RAG) to preserve entities, roles, and relationships.',
              '',
              '[User Instruction]',
              continueUserInstruction.value.trim(),
              '',
              '[Continuation Outline]',
              continueOutline.value.trim(),
            ].join('\n')
        : undefined
    const result: Operation = await runOperation(projectId.value, {
      type: op,
      input,
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
    })
    operationResult.value = result.output
    let changedChapterIds: string[] = []
    if (result.output && op === 'CONTINUE') {
      changedChapterIds = await applyContinuationOutput(result.output)
    } else if (result.output && op === 'CREATE') {
      changedChapterIds = await applyCreateOutput(result.output)
    }
    toast.success('Operation completed')
    await ensureChapterStateInitialized()
    await projectStore.fetchOperations(projectId.value)
    if (changedChapterIds.length) {
      void triggerIncrementalGraphRefresh(changedChapterIds)
    }
  } catch (e: any) {
    operationError.value = parseError(e, 'Operation failed')
  } finally {
    operationLoading.value = false
  }
}

async function handleGenerateCreateOutline() {
  if (!isWorkspaceEmpty.value) {
    createOutlineError.value = 'CREATE outline is only available when workspace text length is 0.'
    return
  }
  if (!createUserPrompt.value.trim()) {
    createOutlineError.value = 'Please provide a creation prompt first.'
    return
  }
  createOutlineLoading.value = true
  createOutlineError.value = null
  operationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const input = [
      'Generate a detailed writing outline first.',
      'Output sections: Theme, Plot Arc, Chapter Beats, Character Goals, Risks, Cliffhangers.',
      'Do not use graph retrieval context in this stage; rely on user prompt only.',
      '',
      '[User Prompt]',
      createUserPrompt.value.trim(),
    ].join('\n')
    const result = await runOperation(projectId.value, {
      type: 'CREATE',
      input,
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      use_rag: false,
    })
    createOutline.value = result.output?.trim() || ''
    if (!createOutline.value) {
      createOutlineError.value = 'No outline returned. Please retry.'
      return
    }
    operationResult.value = createOutline.value
    toast.success('Outline generated')
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    createOutlineError.value = parseError(e, 'Failed to generate outline')
  } finally {
    createOutlineLoading.value = false
  }
}

async function handleGenerateContinueOutline() {
  if (!graphReady.value) {
    continueOutlineError.value = 'Knowledge graph is required before generating continuation outline.'
    return
  }
  if (!continueUserInstruction.value.trim()) {
    continueOutlineError.value = 'Please provide continuation instruction first.'
    return
  }
  continueOutlineLoading.value = true
  continueOutlineError.value = null
  operationError.value = null
  try {
    await persistActiveChapterDraftIfNeeded()
    const result = await runOperation(projectId.value, {
      type: 'ANALYZE',
      input: [
        'Generate a continuation outline before writing the next chapter.',
        'Use RAG context to summarize prior content and character states first, then output follow-up outline.',
        'Output sections: Prior Story Summary, Character State Board, Continuation Goal, Story Beats, Risk Checks, Writing Instructions.',
        '',
        '[User Instruction]',
        continueUserInstruction.value.trim(),
        '',
        '[Selected Chapter Scope]',
        selectedChapters.value.map((chapter) => chapter.title || chapter.id).join(', ') || 'Current chapter only',
      ].join('\n'),
      model: operationModel.value || undefined,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
    })
    continueOutline.value = result.output?.trim() || ''
    if (!continueOutline.value) {
      continueOutlineError.value = 'No continuation outline returned. Please retry.'
      return
    }
    operationResult.value = continueOutline.value
    toast.success('Continuation outline generated')
    await projectStore.fetchOperations(projectId.value)
  } catch (e: any) {
    continueOutlineError.value = parseError(e, 'Failed to generate continuation outline')
  } finally {
    continueOutlineLoading.value = false
  }
}

function canConfirmSimulation(sim: SimulationRuntime): boolean {
  return ['ready', 'completed', 'stopped'].includes((sim.status || '').toLowerCase())
}

function confirmSimulationForContinue(simulationId: string) {
  confirmedSimulationId.value = simulationId
  operationError.value = null
  toast.success('Simulation confirmed for continuation')
}

async function handleGenerateOntology() {
  if (ontologyLoading.value || !graphCanBuild.value) return
  ontologyLoading.value = true
  ontologyError.value = null
  pipelineTaskError.value = null
  ontologyProgress.value = 5
  ontologyMessage.value = 'Preparing ontology generation...'
  graphParsingFile.value = null
  let started = false
  try {
    await persistActiveChapterDraftIfNeeded()
    const sourceText = await resolveWorkflowRequestText('ontology')
    const response = await startGenerateOntologyTask(
      projectId.value,
      {
        text: sourceText || undefined,
        requirement: ontologyRequirement.value || undefined,
        model: ontologyModel.value || undefined,
        chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      }
    )
    started = true
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success('Ontology task started')
  } catch (e: any) {
    ontologyError.value = parseError(e, 'Failed to generate ontology')
  } finally {
    graphParsingFile.value = null
    if (!started) {
      ontologyLoading.value = false
    }
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
  pipelineTaskError.value = null
  graphBuildProgress.value = 5
  graphBuildMessage.value = 'Preparing graph build...'
  graphParsingFile.value = null
  let started = false
  try {
    await persistActiveChapterDraftIfNeeded()
    const sourceText = await resolveWorkflowRequestText('build')
    const response = await startBuildGraphTask(projectId.value, {
      text: sourceText || undefined,
      ontology: ontologyData.value,
      chapter_ids: selectedChapterIds.value.length ? selectedChapterIds.value : undefined,
      build_mode: graphBuildMode.value,
    })
    started = true
    pipelineTask.value = response.task
    upsertTaskListItem(response.task)
    syncPipelineProgress(response.task)
    taskCenterExpanded.value = true
    startPipelineTaskPolling(response.task.task_id)
    toast.success(
      graphBuildMode.value === 'incremental'
        ? 'Incremental graph update task started'
        : 'Graph rebuild task started'
    )
  } catch (e: any) {
    graphError.value = parseError(e, 'Failed to build graph')
  } finally {
    graphParsingFile.value = null
    if (!started) {
      graphLoading.value = false
    }
  }
}

async function handleGraphAnalysis() {
  if (graphAnalysisLoading.value || oasisTaskPolling.value || !graphReady.value) return
  graphAnalysisLoading.value = true
  graphAnalysisError.value = null
  graphAnalysisResult.value = null
  continueOutline.value = ''
  continueOutlineError.value = null
  oasisPackage.value = null
  oasisRunResult.value = null
  oasisReport.value = null
  oasisTaskError.value = null
  oasisPrepareError.value = null
  try {
    const sourceText = graphInputCacheText.value.trim()
      ? graphInputCacheText.value
      : content.value.trim()
    const result = await startAnalyzeOasisTask(projectId.value, {
      text: sourceText || undefined,
      prompt: graphAnalysisPrompt.value.trim() || undefined,
      requirement: ontologyRequirement.value.trim() || undefined,
      analysis_model: oasisAnalysisModel.value || undefined,
      simulation_model: oasisSimulationModel.value || undefined,
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS analysis task started')
  } catch (e: any) {
    graphAnalysisError.value = parseError(e, 'Graph analysis failed')
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
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
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
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
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
      chapter_ids: selectedChapterIds.value,
    })
    oasisTask.value = result.task
    upsertTaskListItem(result.task)
    taskCenterExpanded.value = true
    startOasisTaskPolling(result.task.task_id)
    toast.success('OASIS report task started')
  } catch (e: any) {
    oasisTaskError.value = parseError(e, 'Failed to start OASIS report task')
  }
}

async function loadGraphData(options: { preserveOnError?: boolean } = {}) {
  try {
    graphData.value = await getVisualization(projectId.value)
  } catch {
    if (!options.preserveOnError) {
      graphData.value = { nodes: [], edges: [] }
    }
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
    PENDING: 'text-stone-500 dark:text-zinc-400',
  }
  return colors[status] || 'text-stone-500 dark:text-zinc-400'
}

function oasisTaskStatusColor(status: string) {
  const colors: Record<string, string> = {
    completed: 'text-emerald-700 dark:text-emerald-300',
    failed: 'text-red-700 dark:text-red-300',
    cancelled: 'text-stone-600 dark:text-zinc-400',
    processing: 'text-amber-700 dark:text-amber-300',
    pending: 'text-stone-700 dark:text-zinc-300',
  }
  return colors[status] || 'text-stone-700 dark:text-zinc-300'
}

function oasisStageClass(done: boolean) {
  return done
    ? 'border-emerald-300/70 bg-emerald-100/70 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300'
    : 'border-stone-300 dark:border-zinc-700 bg-stone-100/80 dark:bg-zinc-800/60 text-stone-500 dark:text-zinc-400'
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const [chatModels, embedModels] = await Promise.all([
      getModels(),
      getEmbeddingModels(),
    ])
    models.value = chatModels
    embeddingModels.value = embedModels
  } catch {
    models.value = []
    embeddingModels.value = []
  } finally {
    modelsLoading.value = false
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleGlobalPointerDown)
  document.addEventListener('keydown', handleGlobalKeyDown)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('resize', handleWindowResize)
  applyResponsivePanelPreference(true)
  startTaskListPolling()
  loadProject()
  loadModels()
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleGlobalPointerDown)
  document.removeEventListener('keydown', handleGlobalKeyDown)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('resize', handleWindowResize)
  stopTaskListPolling()
  stopPipelineTaskPolling()
  stopOasisTaskPolling()
})

watch([workflowSourceText, selectedChapterIds], () => {
  graphInputCacheText.value = ''
}, { deep: true })

watch(operationType, (type) => {
  operationError.value = null
  operationResult.value = null
  if (type === 'CONTINUE' && !['append', 'replace', 'new_chapter'].includes(continuationApplyMode.value)) {
    continuationApplyMode.value = 'new_chapter'
  }
  if (type !== 'CREATE') {
    createOutlineError.value = null
  }
  if (type !== 'CONTINUE') {
    continueOutlineError.value = null
  }
})

watch(createUserPrompt, () => {
  createOutline.value = ''
  createOutlineError.value = null
})

watch(continueUserInstruction, () => {
  continueOutline.value = ''
  continueOutlineError.value = null
})

watch(
  () => route.params.id,
  () => {
    if (route.params.id) {
      closeChapterContextMenu()
      projectTitleEditing.value = false
      projectTitleSaving.value = false
      chapterSearchQuery.value = ''
      inlineRenameChapterId.value = ''
      inlineRenameChapterTitle.value = ''
      taskCenterExpanded.value = false
      cancellingTaskIds.value = []
      stopPipelineTaskPolling()
      stopOasisTaskPolling()
      taskList.value = []
      taskListLoading.value = false
      taskListError.value = null
      pipelineTask.value = null
      pipelineTaskError.value = null
      oasisTaskLastId.value = ''
      graphData.value = { nodes: [], edges: [] }
      graphLoading.value = false
      graphError.value = null
      graphBuildMessage.value = ''
      graphBuildProgress.value = 0
      ontologyLoading.value = false
      ontologyError.value = null
      ontologyMessage.value = ''
      ontologyProgress.value = 0
      ontologyData.value = null
      oasisAnalysisData.value = null
      graphAnalysisLoading.value = false
      graphAnalysisResult.value = null
      graphAnalysisError.value = null
      oasisPackage.value = null
      oasisRunResult.value = null
      oasisReport.value = null
      oasisPrepareError.value = null
      oasisTask.value = null
      oasisTaskError.value = null
      createUserPrompt.value = ''
      createOutline.value = ''
      createOutlineError.value = null
      continueUserInstruction.value = ''
      continueOutline.value = ''
      continueOutlineError.value = null
      confirmedSimulationId.value = ''
      loadProject()
    }
  }
)

watch(activeChapterId, () => {
  syncActiveChapterContentFromState()
})

watch(
  () => projectSimulations.value.map((sim) => sim.simulation_id),
  (ids) => {
    if (confirmedSimulationId.value && !ids.includes(confirmedSimulationId.value)) {
      confirmedSimulationId.value = ''
    }
  }
)

watch(selectedChapterIds, () => {
  closeChapterContextMenu()
  continueOutline.value = ''
  continueOutlineError.value = null
  confirmedSimulationId.value = ''
})
</script>

<template>
  <AppLayout :padded="false">
    <div v-if="projectStore.projectLoading" class="flex items-center justify-center h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent" />
    </div>

    <div v-else-if="!projectStore.currentProject" class="flex items-center justify-center h-full">
      <p class="text-stone-500 dark:text-zinc-500">Project not found</p>
    </div>

    <div v-else class="h-full flex flex-col bg-[#f7f3e8] text-stone-800 dark:bg-zinc-900 dark:text-zinc-100">
      <div class="flex items-center justify-between gap-3 border-b border-stone-300/80 px-4 py-2.5 dark:border-zinc-700/60">
        <div class="min-w-0">
          <div v-if="projectTitleEditing" class="flex flex-wrap items-center gap-2">
            <Input
              v-model="projectTitleDraft"
              class="h-8 min-w-[220px] max-w-[420px]"
              placeholder="Project name"
              @keydown.enter.prevent="submitProjectTitleEdit"
              @keydown.esc.prevent="cancelProjectTitleEdit"
            />
            <Button
              variant="secondary"
              size="sm"
              :loading="projectTitleSaving"
              @click="submitProjectTitleEdit"
            >
              Save
            </Button>
            <Button
              variant="ghost"
              size="sm"
              :disabled="projectTitleSaving"
              @click="cancelProjectTitleEdit"
            >
              Cancel
            </Button>
          </div>
          <Button
            v-else
            variant="ghost"
            size="sm"
            class="h-auto min-h-0 px-0 py-0 text-left hover:bg-transparent dark:hover:bg-transparent"
            @click="beginProjectTitleEdit"
          >
            <h1 class="truncate text-sm font-semibold sm:text-base">
              {{ projectStore.currentProject.title }}
            </h1>
          </Button>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-2 sm:flex-nowrap">
          <Button variant="secondary" size="sm" @click="toggleLeftPanel">
            {{ leftPanelCollapsed ? 'Show Files' : 'Hide Files' }}
          </Button>
          <Button variant="secondary" size="sm" @click="toggleRightPanel">
            {{ rightPanelCollapsed ? 'Show AI' : 'Hide AI' }}
          </Button>
          <Button variant="secondary" size="sm" :loading="saving" @click="handleSave">
            <Save class="w-4 h-4" />
            Save
          </Button>
        </div>
      </div>

      <div class="flex flex-1 overflow-hidden">
        <!-- Left: File Explorer -->
        <aside
          class="shrink-0 border-r border-stone-300/80 bg-[#f2ecdf] transition-all duration-200 dark:border-zinc-700/60 dark:bg-zinc-900/50"
          :class="leftPanelCollapsed ? 'w-0 overflow-hidden border-r-0 p-0' : 'w-72 p-3'"
        >
          <template v-if="!leftPanelCollapsed">
          <input
            ref="chapterFileInput"
            type="file"
            multiple
            :accept="GRAPH_DOCUMENT_ACCEPT"
            class="hidden"
            @change="handleChapterFileSelect"
          />

          <div class="mb-3 flex items-center justify-between">
            <p class="text-[11px] uppercase tracking-wider text-stone-500 dark:text-zinc-500">
              Files (Chapters)
            </p>
            <span class="text-[10px] text-stone-500 dark:text-zinc-500">
              Scope {{ selectedChapterIds.length }}
            </span>
          </div>

          <div class="mb-3 flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" :disabled="projectStore.chapterSaving" @click="handleCreateChapter">+ Chapter</Button>
            <Button variant="ghost" size="sm" :loading="chapterImporting" :disabled="chapterImporting" @click="openChapterFilePicker">
              Import
            </Button>
            <Button variant="ghost" size="sm" :disabled="projectStore.chapterSaving || projectStore.orderedChapters.length <= 1" @click="handleDeleteActiveChapter">Delete</Button>
          </div>

          <Input
            v-model="chapterSearchQuery"
            class="mb-2"
            placeholder="搜索章节 / Search chapters"
          />

          <p v-if="chapterImportMessage" class="mb-2 text-xs text-amber-700 dark:text-amber-300">
            {{ chapterImportMessage }}
          </p>

          <div class="max-h-[calc(100%-150px)] space-y-1 overflow-y-auto pr-1">
            <div
              v-for="chapter in filteredChapters"
              :key="`scope-${chapter.id}`"
              class="flex items-center gap-2 rounded border px-2 py-1.5 transition-colors"
              :class="
                activeChapterId === chapter.id
                  ? 'border-amber-500/70 bg-amber-100/70 dark:bg-amber-900/20'
                  : 'border-stone-300 bg-stone-50/80 hover:bg-stone-100 dark:border-zinc-700 dark:bg-zinc-800/60 dark:hover:bg-zinc-800'
              "
              @contextmenu.prevent="openChapterContextMenu($event, chapter.id)"
            >
              <Checkbox
                :model-value="selectedChapterIds.includes(chapter.id)"
                @click.stop
                @update:modelValue="() => toggleChapterForWorkflow(chapter.id)"
              />
              <div class="min-w-0 flex-1 cursor-pointer" @click="handleSelectChapter(chapter.id)">
                <input
                  v-if="isInlineRenamingChapter(chapter.id)"
                  ref="inlineRenameInputRef"
                  v-model="inlineRenameChapterTitle"
                  class="h-7 w-full rounded-md border border-amber-400 bg-stone-50 px-2 text-xs font-medium text-stone-800 outline-none ring-2 ring-amber-300/40 dark:border-amber-500/70 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-amber-500/30"
                  :disabled="inlineRenameSubmitting"
                  @click.stop
                  @keydown.enter.prevent="submitInlineRenameChapter"
                  @keydown.esc.prevent="cancelInlineRenameChapter"
                  @blur="submitInlineRenameChapter"
                />
                <p
                  v-else
                  class="truncate text-xs font-medium"
                  :class="activeChapterId === chapter.id ? 'text-amber-700 dark:text-amber-300' : 'text-stone-700 dark:text-zinc-200'"
                  @dblclick.stop="beginInlineRenameChapter(chapter.id)"
                >
                  {{ chapter.title || `Chapter ${chapter.order_index + 1}` }}
                </p>
                <p class="text-[10px] text-stone-500 dark:text-zinc-500">
                  #{{ chapter.order_index + 1 }} · {{ (chapter.content || '').length.toLocaleString() }} chars
                </p>
              </div>
            </div>
            <p v-if="!filteredChapters.length" class="px-1 py-2 text-xs text-stone-500 dark:text-zinc-500">
              没有匹配章节
            </p>
          </div>
          </template>
        </aside>

        <!-- Center: Editor -->
        <section
          v-show="!(isMobileLayout && !rightPanelCollapsed)"
          class="min-w-0 flex-1 bg-[#fbf8f1] dark:bg-zinc-900/30"
          :class="rightPanelCollapsed ? '' : 'border-r border-stone-300/80 dark:border-zinc-700/60'"
        >
          <div class="flex items-center justify-between border-b border-stone-300/70 px-4 py-2 dark:border-zinc-700/60">
            <p class="truncate text-sm font-medium text-stone-700 dark:text-zinc-200">
              {{ findChapterById(activeChapterId)?.title || 'Untitled Chapter' }}
            </p>
            <span class="text-xs text-stone-500 dark:text-zinc-500">
              {{ content.length.toLocaleString() }} chars
            </span>
          </div>
          <div class="h-[calc(100%-43px)] p-4">
            <TextEditor v-model="content" placeholder="Write chapter content here..." />
          </div>
        </section>

        <!-- Right: AI Operations Panel -->
        <div
          class="shrink-0 flex flex-col overflow-hidden transition-all duration-200 bg-[#f7f3ea] dark:bg-zinc-900/70"
          :class="
            rightPanelCollapsed
              ? 'w-0 min-w-0 max-w-0'
              : (isMobileLayout ? 'w-full min-w-0 max-w-none' : 'w-[44%] min-w-[420px] max-w-[760px]')
          "
        >
        <div class="px-5 py-4 border-b border-stone-300/70 dark:border-zinc-700/50 space-y-3">
          <div>
            <p class="text-[11px] uppercase tracking-[0.16em] text-stone-500 dark:text-zinc-400">
              AI Operations
            </p>
            <p class="text-base font-semibold text-stone-800 dark:text-zinc-100">
              Graph, Create, OASIS
            </p>
          </div>
          <Tabs v-model="rightPanelTab" class="w-full">
            <TabsList class="grid h-auto w-full grid-cols-3 gap-1 rounded-xl border border-stone-200/90 bg-stone-100/90 p-1 dark:border-zinc-700/70 dark:bg-zinc-800/80">
              <TabsTrigger
                v-for="tab in rightPanelTabs"
                :key="tab.key"
                :value="tab.key"
                class="py-2.5"
              >
                <component :is="tab.icon" class="h-3.5 w-3.5" />
                {{ tab.label }}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <!-- AI Tab -->
        <div v-show="rightPanelTab !== 'graph'" class="flex-1 overflow-y-auto p-5 lg:p-6 space-y-5">
          <Alert
            v-if="!graphReady && (rightPanelTab === 'oasis' || (rightPanelTab === 'ai' && operationType !== 'CREATE'))"
            variant="warning"
          >
            RAG requires a built graph first. Complete Graph Build before this operation or OASIS simulation.
            <Button
              variant="ghost"
              size="sm"
              class="ml-1 h-auto px-0 py-0 underline decoration-dotted hover:bg-transparent hover:text-amber-700 dark:hover:bg-transparent dark:hover:text-amber-100"
              @click="rightPanelTab = 'graph'"
            >
              Go build graph
            </Button>
          </Alert>

          <div v-show="rightPanelTab === 'ai'" class="space-y-5">
          <!-- Operation Type -->
          <div class="grid grid-cols-2 gap-2.5">
            <Button
              v-for="op in operationTypes"
              :key="op.value"
              variant="secondary"
              size="sm"
              class="h-auto justify-start rounded-xl px-3.5 py-2.5 text-sm"
              :class="
                operationType === op.value
                  ? 'border-amber-500 bg-amber-600/20 text-amber-700 dark:text-amber-300'
                  : 'text-stone-500 dark:text-zinc-400 hover:border-stone-400 dark:hover:border-zinc-600 hover:text-stone-700 dark:hover:text-zinc-200'
              "
              :disabled="op.value === 'CREATE' && !isWorkspaceEmpty"
              @click="operationType = op.value"
            >
              <component :is="op.icon" class="w-4 h-4" />
              {{ op.label }}
            </Button>
          </div>
          <p v-if="!isWorkspaceEmpty" class="text-xs text-amber-700 dark:text-amber-300">
            CREATE mode is only available when workspace text length is 0.
          </p>

          <!-- Model Selector -->
          <div class="space-y-2">
            <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Operation Model</label>
            <Select
              v-model="operationModel"
              :disabled="modelsLoading"
            >
              <option value="">Use backend default</option>
              <option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option>
            </Select>
          </div>

          <div v-if="operationType === 'CONTINUE'" class="space-y-2">
            <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Continuation Apply Mode</label>
            <Select
              v-model="continuationApplyMode"
            >
              <option value="new_chapter">Create new chapter</option>
              <option value="append">Append to editor</option>
              <option value="replace">Replace editor content</option>
            </Select>
          </div>

          <div v-if="operationType === 'CREATE'" class="space-y-2.5 rounded-xl border border-stone-300/80 bg-stone-100/80 p-4 dark:border-zinc-700/60 dark:bg-zinc-800/45">
            <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">Step 0. User Prompt</p>
            <Textarea
              v-model="createUserPrompt"
              :rows="4"
              placeholder="Describe theme, style, setting, and any must-have elements."
              class="min-h-24"
            />
            <div class="flex items-center justify-between">
              <p class="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-300">Step A. Outline First</p>
              <Button
                variant="secondary"
                size="sm"
                :loading="createOutlineLoading"
                :disabled="!isWorkspaceEmpty || !createUserPrompt.trim() || modelsLoading"
                @click="handleGenerateCreateOutline"
              >
                Generate Outline
              </Button>
            </div>
            <Textarea
              v-model="createOutline"
              :rows="8"
              placeholder="Generated outline will appear here. You can edit before drafting."
              class="min-h-44"
            />
            <p class="text-xs text-stone-600 dark:text-zinc-300/90">
              CREATE is locked to empty workspace. Outline stage uses user prompt directly (without RAG).
            </p>
            <p v-if="createOutlineError" class="text-xs text-red-700 dark:text-red-300">{{ createOutlineError }}</p>
          </div>

          <div v-if="operationType === 'CONTINUE'" class="space-y-2.5 rounded-xl border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-4">
            <p class="text-xs font-medium uppercase tracking-wider text-stone-700 dark:text-zinc-300">Continue Prerequisites</p>
            <Textarea
              v-model="continueUserInstruction"
              :rows="4"
              placeholder="Describe what should happen next and any writing constraints."
              class="min-h-24"
            />
            <Button
              variant="secondary"
              size="sm"
              :loading="continueOutlineLoading"
              :disabled="!graphReady || !continueUserInstruction.trim() || modelsLoading"
              @click="handleGenerateContinueOutline"
            >
              1. Generate Continuation Outline
            </Button>
            <Textarea
              v-model="continueOutline"
              :rows="7"
              placeholder="Continuation outline and checks from graph analysis will appear here."
              class="min-h-36"
            />
            <p v-if="continueOutlineError" class="text-xs text-red-700 dark:text-red-300">{{ continueOutlineError }}</p>
            <div class="space-y-1 text-xs">
              <p :class="graphReady ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
                {{ graphReady ? '✓' : '•' }} RAG graph context available
              </p>
              <p :class="continueUserInstruction.trim() ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
                {{ continueUserInstruction.trim() ? '✓' : '•' }} Continuation instruction provided
              </p>
              <p :class="continueOutline.trim() ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
                {{ continueOutline.trim() ? '✓' : '•' }} Continuation outline generated and reviewed
              </p>
            </div>
            <p class="text-[11px] text-stone-500 dark:text-zinc-400">
              Continue mode can auto-create a new chapter from LLM output.
            </p>
          </div>

          <Alert variant="warning">
            Upload is only available in the left File Manager. Continue/analysis runs with selected chapter scope and RAG.
          </Alert>

          <Button
            variant="secondary"
            class="w-full"
            :loading="operationLoading"
            :disabled="
              (operationType !== 'CREATE' && !graphReady)
              || modelsLoading
              || (operationType === 'CREATE' && !createPrerequisitesReady)
              || (operationType === 'CONTINUE' && !continuePrerequisitesReady)
            "
            @click="handleOperation"
          >
            <Sparkles class="w-4 h-4" />
            {{ operationPrimaryLabel }}
          </Button>
          <p v-if="operationType !== 'CREATE' && !graphReady" class="text-xs text-amber-700 dark:text-amber-300">
            Build graph first. This operation requires RAG context.
          </p>

          <!-- Result -->
          <Alert v-if="operationError" variant="destructive" class="text-sm">
            {{ operationError }}
          </Alert>

          <div v-if="operationResult" class="space-y-2">
            <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Result</h3>
            <div class="rounded-lg border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/80 dark:bg-zinc-800/50 p-3 text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
              {{ operationResult }}
            </div>
          </div>

          <!-- Operation History -->
          <div v-if="projectStore.operations.length > 0" class="space-y-2">
            <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">History</h3>
            <div class="space-y-1.5 max-h-60 overflow-y-auto">
              <div
                v-for="op in projectStore.operations"
                :key="op.id"
                class="rounded-lg border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/70 dark:bg-zinc-800/30 px-3 py-2"
              >
                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-stone-700 dark:text-zinc-300">{{ op.type }}</span>
                  <span :class="statusColor(op.status)" class="text-xs">{{ op.status }}</span>
                </div>
                <div class="flex items-center gap-2 mt-1 text-xs text-stone-500 dark:text-zinc-500">
                  <span>{{ op.model }}</span>
                  <span>{{ formatDate(op.created_at) }}</span>
                </div>
                <p v-if="op.output" class="text-xs text-stone-500 dark:text-zinc-400 mt-1 line-clamp-2">{{ op.output }}</p>
              </div>
            </div>
          </div>
          </div>

          <Card v-show="rightPanelTab === 'oasis'" class="space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">Workflow</h3>
              <Button variant="ghost" size="sm" :loading="simulationLoading" @click="loadProjectSimulations">
                Refresh
              </Button>
            </div>
            <p class="text-xs text-stone-500 dark:text-zinc-500">
              Continue workflow: graph analysis -> create simulation -> confirm simulation -> run continue.
            </p>
            <Button
              variant="secondary"
              class="w-full"
              :loading="simulationCreating"
              :disabled="!graphReady"
              @click="handleCreateWorkflowSimulation"
            >
              <Sparkles class="w-4 h-4" />
              Create Simulation
            </Button>
            <p v-if="!graphReady" class="text-xs text-amber-700 dark:text-amber-300">
              Build graph first, then create workflow simulation.
            </p>
            <Alert v-if="simulationError" variant="destructive" class="text-sm">
              {{ simulationError }}
            </Alert>
            <div v-if="projectSimulations.length > 0" class="space-y-1.5 max-h-52 overflow-y-auto">
              <div
                v-for="sim in projectSimulations.slice(0, 8)"
                :key="sim.simulation_id"
                class="rounded-lg border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/75 dark:bg-zinc-800/40 px-3 py-2"
              >
                <div class="flex items-center justify-between gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    class="h-auto min-w-0 justify-start px-0 py-0 text-left hover:bg-transparent dark:hover:bg-transparent"
                    @click="router.push(`/simulation/${sim.simulation_id}`)"
                  >
                    <p class="text-xs font-medium text-stone-700 dark:text-zinc-300">{{ sim.simulation_id.slice(0, 12) }}...</p>
                    <p class="text-[11px] text-stone-500 dark:text-zinc-500 mt-1">{{ sim.updated_at || sim.created_at || '-' }}</p>
                  </Button>
                  <div class="flex items-center gap-2">
                    <span class="text-xs text-stone-500 dark:text-zinc-500 capitalize">{{ sim.status }}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      class="h-auto px-2 py-1 text-[11px]"
                      :class="
                        confirmedSimulationId === sim.simulation_id
                          ? 'border-emerald-600 bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'
                          : canConfirmSimulation(sim)
                            ? 'border-amber-600/70 text-amber-700 dark:text-amber-300 hover:border-amber-500'
                            : 'border-stone-300 dark:border-zinc-700 text-stone-500 dark:text-zinc-500 cursor-not-allowed'
                      "
                      :disabled="!canConfirmSimulation(sim)"
                      @click="confirmSimulationForContinue(sim.simulation_id)"
                    >
                      {{ confirmedSimulationId === sim.simulation_id ? 'Confirmed' : 'Confirm' }}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>

        <!-- Graph Tab -->
        <div v-show="rightPanelTab !== 'ai'" class="flex-1 overflow-y-auto p-5 lg:p-6 space-y-5 border-t border-stone-300/60 dark:border-zinc-700/40">
          <Card
            v-show="rightPanelTab === 'graph'"
            class="space-y-4 !rounded-xl !border-stone-300/80 !bg-[#f3ede1] dark:!border-zinc-700/60 dark:!bg-zinc-800/55 !p-5"
          >
            <div class="space-y-2">
              <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                Step 1. Ontology Generation
              </h3>
              <div class="rounded-lg border border-amber-700/30 bg-amber-900/10 p-3 space-y-1.5">
                <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
                  用途：先定义实体/关系本体，作为 RAG 检索与图谱入库的结构约束。
                </p>
                <p class="text-xs text-amber-700 dark:text-amber-300/90">
                  未完成本体生成时，Step 2 图谱构建不可执行，AI 创作与 OASIS 模拟也会缺少可靠上下文。
                </p>
                <p class="text-xs text-amber-700 dark:text-amber-300/80">
                  数据源始终来自左侧已选章节，当前文本长度：{{ workflowSourceText.length.toLocaleString() }} characters
                </p>
              </div>
            </div>

            <div class="space-y-2.5">
              <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                Requirement Preset
              </label>
              <Textarea
                v-model="ontologyRequirement"
                :rows="5"
                placeholder="Edit ontology requirement preset"
                class="min-h-28"
              />
              <p class="text-[11px] text-stone-500 dark:text-zinc-500">
                Preset prompt is enabled by default. You can edit it before each generation.
              </p>
            </div>

            <div class="space-y-2">
              <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                Ontology Model
              </label>
              <Select
                v-model="ontologyModel"
                :disabled="modelsLoading"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`ontology-${m.id}`" :value="m.id">{{ m.name }}</option>
              </Select>
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
              <div class="flex items-center justify-between text-xs text-stone-500 dark:text-zinc-400">
                <span>{{ ontologyMessage || 'Processing...' }}</span>
                <span>{{ ontologyProgress }}%</span>
              </div>
              <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
                <div
                  class="h-full bg-amber-500 transition-all duration-300"
                  :style="{ width: `${ontologyProgress}%` }"
                />
              </div>
              <p v-if="graphParsingFile" class="text-xs text-stone-500 dark:text-zinc-500 truncate">
                Parsing: {{ graphParsingFile }}
              </p>
            </div>

            <Alert v-if="ontologyError" variant="destructive" class="text-sm">
              {{ ontologyError }}
            </Alert>

            <Alert
              v-if="ontologyData && !hasOntology && !ontologyLoading"
              variant="destructive"
              class="text-sm"
            >
              Current ontology is invalid for graph build. Regenerate ontology until valid structured output is returned.
            </Alert>

            <div v-if="hasOntology" class="rounded-lg border border-emerald-700/40 bg-emerald-900/10 p-3 space-y-2">
              <div class="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-300">
                <span>Ontology ready</span>
                <span>{{ ontologyData?.entity_types?.length || 0 }} entities / {{ ontologyData?.edge_types?.length || 0 }} relations</span>
              </div>
              <div class="space-y-1 text-[11px] text-stone-600 dark:text-zinc-300">
                <p v-if="ontologyMeta?.model">
                  Model:
                  <span class="font-medium">{{ ontologyMeta.model }}</span>
                  <span v-if="ontologyMeta?.provider"> · {{ ontologyMeta.provider }}</span>
                </p>
                <p v-if="ontologyMeta?.api_called">
                  Tokens: {{ ontologyMeta?.input_tokens || 0 }} in / {{ ontologyMeta?.output_tokens || 0 }} out
                </p>
              </div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="entity in (ontologyData?.entity_types || []).slice(0, 8)"
                  :key="entity.name"
                  class="rounded-full bg-stone-200/80 dark:bg-zinc-800/80 px-2 py-0.5 text-xs text-stone-700 dark:text-zinc-300"
                >
                  {{ entity.name }}
                </span>
              </div>
            </div>
          </Card>

          <Card
            v-show="rightPanelTab === 'graph'"
            class="space-y-4 !rounded-xl !border-stone-300/80 !bg-[#f3ede1] dark:!border-zinc-700/60 dark:!bg-zinc-800/55 !p-5"
          >
            <div class="space-y-2.5">
              <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                Step 2. Graph Build
              </h3>
              <div class="space-y-2">
                <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                  Graph Build Model
                </label>
                <Select
                  v-model="graphBuildModel"
                  :disabled="modelsLoading"
                >
                  <option value="">Use backend default</option>
                  <option v-for="m in models" :key="`graph-build-${m.id}`" :value="m.id">{{ m.name }}</option>
                </Select>
              </div>
              <div class="space-y-2">
                <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                  Embedding Model
                </label>
                <Select
                  v-model="graphEmbeddingModel"
                  :disabled="modelsLoading"
                >
                  <option value="">Use backend auto select</option>
                  <option
                    v-for="m in embeddingModels"
                    :key="`graph-embed-${m.id}`"
                    :value="m.id"
                  >
                    {{ m.name }}
                  </option>
                </Select>
              </div>
              <div class="space-y-2">
                <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                  Reranker Model (Optional)
                </label>
                <Select
                  v-model="graphRerankerModel"
                  :disabled="modelsLoading"
                >
                  <option value="">Disabled</option>
                  <option v-for="m in models" :key="`graph-reranker-${m.id}`" :value="m.id">{{ m.name }}</option>
                </Select>
                <p class="text-[11px] text-stone-500 dark:text-zinc-500">
                  Used for RAG retrieval re-ranking in graph search and AI operations.
                </p>
              </div>
              <div class="space-y-2">
                <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                  Build Mode
                </label>
                <Select v-model="graphBuildMode">
                  <option value="rebuild">From Zero (Clear Old Graph)</option>
                  <option value="incremental">Incremental Update (Changed Chapters Only)</option>
                </Select>
                <p class="text-[11px] text-stone-500 dark:text-zinc-500">
                  Rebuild ensures a clean graph. Incremental mode appends only changed chapter content.
                </p>
              </div>
              <Button
                variant="primary"
                class="w-full"
                :loading="graphLoading"
                :disabled="!graphCanBuild || !hasOntology"
                @click="handleBuildGraph"
              >
                <Network class="w-4 h-4" />
                {{ graphBuildActionLabel }}
              </Button>
            </div>

            <div v-if="graphLoading || graphBuildMessage" class="space-y-1">
              <div class="flex items-center justify-between text-xs text-stone-500 dark:text-zinc-400">
                <span>{{ graphBuildMessage || 'Processing...' }}</span>
                <span>{{ graphBuildProgress }}%</span>
              </div>
              <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
                <div
                  class="h-full bg-amber-500 transition-all duration-300"
                  :style="{ width: `${graphBuildProgress}%` }"
                />
              </div>
              <p v-if="graphParsingFile" class="text-xs text-stone-500 dark:text-zinc-500 truncate">
                Parsing: {{ graphParsingFile }}
              </p>
            </div>

            <p v-if="!hasOntology" class="text-xs text-amber-700 dark:text-amber-300">
              Please complete Step 1 first.
            </p>

            <Alert v-if="graphError" variant="destructive" class="text-sm">
              {{ graphError }}
            </Alert>
          </Card>

          <Card v-show="rightPanelTab === 'oasis'" class="space-y-4">
            <h3 class="text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
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
            <Textarea
              v-model="graphAnalysisPrompt"
              :rows="2"
              placeholder="Enter OASIS analysis focus"
              class="min-h-24"
            />
            <div class="space-y-2">
              <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                OASIS Analysis Model
              </label>
              <Select
                v-model="oasisAnalysisModel"
                :disabled="modelsLoading"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-analysis-${m.id}`" :value="m.id">{{ m.name }}</option>
              </Select>
            </div>
            <div class="space-y-2">
              <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                OASIS Simulation Model
              </label>
              <Select
                v-model="oasisSimulationModel"
                :disabled="modelsLoading"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-sim-${m.id}`" :value="m.id">{{ m.name }}</option>
              </Select>
            </div>
            <div class="space-y-2">
              <label class="block text-xs font-medium text-stone-500 dark:text-zinc-400 uppercase tracking-wider">
                OASIS Report Model
              </label>
              <Select
                v-model="oasisReportModel"
                :disabled="modelsLoading"
              >
                <option value="">Use backend default</option>
                <option v-for="m in models" :key="`oasis-report-${m.id}`" :value="m.id">{{ m.name }}</option>
              </Select>
            </div>
            <Button
              variant="secondary"
              class="w-full"
              :loading="graphAnalysisLoading"
              :disabled="!graphReady || oasisTaskPolling"
              @click="handleGraphAnalysis"
            >
              <Search class="w-4 h-4" />
              Run OASIS Analysis
            </Button>
            <Button
              variant="ghost"
              class="w-full"
              :loading="oasisPrepareLoading || (oasisTaskPolling && oasisTask?.task_type === 'oasis_prepare')"
              :disabled="!graphReady || !hasOasisAnalysis || oasisTaskPolling"
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
            <p v-if="!graphReady" class="text-xs text-amber-700 dark:text-amber-300">Build graph before analysis.</p>
            <Alert v-if="graphAnalysisError" variant="destructive" class="text-sm">
              {{ graphAnalysisError }}
            </Alert>
            <Alert v-if="oasisPrepareError" variant="destructive" class="text-sm">
              {{ oasisPrepareError }}
            </Alert>
            <Alert v-if="oasisTaskError" variant="destructive" class="text-sm">
              {{ oasisTaskError }}
            </Alert>
            <div
              v-if="oasisTask"
              class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-xs text-stone-700 dark:text-zinc-200 space-y-2"
            >
              <div class="flex items-center justify-between">
                <span class="uppercase tracking-wider text-stone-500 dark:text-zinc-400">{{ oasisTask.task_type }}</span>
                <span class="capitalize" :class="oasisTaskStatusColor(oasisTask.status)">{{ oasisTask.status }}</span>
              </div>
              <p class="text-stone-700 dark:text-zinc-300">{{ oasisTask.message || 'Processing...' }}</p>
              <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
                <div
                  class="h-full bg-amber-500 transition-all duration-300"
                  :style="{ width: `${oasisTask.progress || 0}%` }"
                />
              </div>
              <div class="flex items-center justify-between gap-2 text-[11px] text-stone-500 dark:text-zinc-400">
                <span>Task ID: {{ oasisTask.task_id }}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  :disabled="oasisTaskPolling"
                  @click="handleRefreshOasisTaskStatus"
                >
                  Refresh status
                </Button>
              </div>
            </div>
            <div
              v-if="!oasisTask && oasisTaskLastId"
              class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-xs text-stone-700 dark:text-zinc-300 space-y-2"
            >
              <p>Last OASIS task: {{ oasisTaskLastId }}</p>
              <Button
                variant="secondary"
                size="sm"
                :disabled="oasisTaskPolling"
                @click="handleRefreshOasisTaskStatus"
              >
                Refresh last task status
              </Button>
            </div>
            <div
              v-if="graphAnalysisResult"
              class="rounded-lg border border-stone-300/80 dark:border-zinc-700/60 bg-stone-100/75 dark:bg-zinc-800/40 p-3 text-sm text-stone-700 dark:text-zinc-200 whitespace-pre-wrap max-h-48 overflow-y-auto"
            >
              {{ graphAnalysisResult }}
            </div>
            <div
              v-if="hasOasisAnalysis"
              class="rounded-lg border border-emerald-300/70 bg-emerald-100 p-3 text-xs text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300"
            >
              OASIS summary ready. Guidance and agent profiles are now used by continuation generation.
            </div>
            <div
              v-if="oasisPackage"
              class="rounded-lg border border-amber-700/30 bg-amber-900/10 p-3 text-xs text-amber-800 dark:text-amber-200 space-y-1"
            >
              <p>Simulation Package: {{ oasisPackage.simulation_id }}</p>
              <p>Profiles: {{ oasisPackage.profiles?.length || 0 }}</p>
              <p>Events: {{ oasisPackage.simulation_config?.events?.length || 0 }}</p>
              <p>Platforms: {{ (oasisPackage.simulation_config?.active_platforms || []).join(', ') || 'N/A' }}</p>
            </div>
            <div
              v-if="oasisRunResult"
              class="rounded-lg border border-stone-300/80 bg-stone-100/75 p-3 text-xs text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200 space-y-1"
            >
              <p>Run: {{ oasisRunResult.run_id }}</p>
              <p>Rounds: {{ oasisRunResult.metrics?.total_rounds || 0 }}</p>
              <p>Active Agents: {{ oasisRunResult.metrics?.active_agents || 0 }}</p>
              <p>Estimated Posts: {{ oasisRunResult.metrics?.estimated_posts || 0 }}</p>
            </div>
            <div
              v-if="oasisReport"
              class="rounded-lg border border-amber-300/80 bg-amber-100/75 p-3 text-xs text-amber-900 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-200 space-y-1"
            >
              <p>Report: {{ oasisReport.report_id }}</p>
              <p class="font-medium">{{ oasisReport.title }}</p>
              <p class="text-amber-800 dark:text-amber-200/90 line-clamp-3">{{ oasisReport.executive_summary }}</p>
            </div>
          </Card>

          <div v-if="rightPanelTab === 'graph' && graphData.nodes.length > 0" class="space-y-4">
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

          <div v-else-if="rightPanelTab === 'graph' && !graphLoading" class="text-center py-8">
            <Network class="w-10 h-10 mx-auto text-stone-600 dark:text-zinc-500 mb-3" />
            <p class="text-sm text-stone-500 dark:text-zinc-500">No graph data yet. Follow steps 1-2 to build the graph.</p>
          </div>

          <GraphSearch v-if="rightPanelTab === 'graph'" :project-id="projectId" />
        </div>

      </div>
    </div>
    </div>

    <Teleport to="body">
      <div class="fixed bottom-4 right-4 z-[95] flex flex-col items-end gap-2">
        <div
          v-if="taskCenterExpanded"
          class="w-[min(92vw,420px)] max-h-[70vh] overflow-hidden rounded-2xl border border-stone-300/80 bg-[#f8f4ea]/95 shadow-2xl backdrop-blur-sm dark:border-zinc-700/70 dark:bg-zinc-900/92"
        >
          <div class="flex items-center justify-between gap-2 border-b border-stone-300/70 px-3 py-2 dark:border-zinc-700/60">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wider text-stone-700 dark:text-zinc-200">
                Task Center
              </p>
              <p class="text-[11px] text-stone-500 dark:text-zinc-500">
                Running {{ runningTaskCount }} / Total {{ taskList.length }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-28">
                <Select v-model="taskListFilter">
                  <option value="all">All</option>
                  <option value="running">Running</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                  <option value="cancelled">Cancelled</option>
                </Select>
              </div>
              <Button
                variant="ghost"
                size="sm"
                :loading="taskListLoading"
                @click="handleRefreshTaskList"
              >
                Refresh
              </Button>
            </div>
          </div>

          <div class="max-h-[58vh] overflow-y-auto px-3 py-2 space-y-2">
            <Alert v-if="taskListError" variant="destructive" class="text-xs">
              {{ taskListError }}
            </Alert>

            <div v-if="filteredTaskList.length" class="space-y-1.5">
              <div
                v-for="task in filteredTaskList"
                :key="task.task_id"
                class="rounded-lg border border-stone-300/70 dark:border-zinc-700/50 bg-stone-100/80 dark:bg-zinc-800/45 p-2 space-y-1.5"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-medium text-stone-700 dark:text-zinc-200">
                    {{ taskTypeLabel(task.task_type) }}
                  </span>
                  <span class="text-xs capitalize" :class="taskStatusClass(task.status)">
                    {{ task.status }}
                  </span>
                </div>
                <p class="text-[11px] text-stone-600 dark:text-zinc-300 line-clamp-2">
                  {{ task.message || '-' }}
                </p>
                <div class="h-1.5 rounded bg-stone-200/70 dark:bg-zinc-800/70 overflow-hidden">
                  <div
                    class="h-full bg-amber-500 transition-all duration-300"
                    :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress || 0)))}%` }"
                  />
                </div>
                <div class="flex items-center justify-between gap-2 text-[10px] text-stone-500 dark:text-zinc-500">
                  <span>{{ formatDate(task.updated_at) }}</span>
                  <span class="truncate max-w-[180px]">#{{ task.task_id }}</span>
                </div>
                <div class="flex items-center justify-between gap-2">
                  <p v-if="task.error" class="min-w-0 flex-1 text-[10px] text-red-700 dark:text-red-300 line-clamp-2">
                    {{ task.error }}
                  </p>
                  <Button
                    v-if="isTaskCancellable(task)"
                    variant="ghost"
                    size="sm"
                    class="h-6 px-2 text-[10px] text-red-700 hover:text-red-700 dark:text-red-300 dark:hover:text-red-200"
                    :loading="isTaskCancelling(task.task_id)"
                    :disabled="isTaskCancelling(task.task_id)"
                    @click="handleCancelTask(task)"
                  >
                    Terminate
                  </Button>
                </div>
              </div>
            </div>
            <p v-else class="text-[11px] text-stone-500 dark:text-zinc-500 py-3 text-center">
              No tasks yet.
            </p>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          class="shadow-xl"
          @click="taskCenterExpanded = !taskCenterExpanded"
        >
          Task Center
          <span class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-black/20 px-1.5 text-[10px] text-white">
            {{ runningTaskCount }}
          </span>
        </Button>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="chapterContextMenu.visible && contextMenuChapter"
        data-chapter-context-menu="true"
        class="fixed z-[90] w-48 rounded-lg border border-stone-300 bg-stone-50 p-1 shadow-xl dark:border-zinc-700 dark:bg-zinc-800"
        :style="chapterContextMenuStyle"
        @contextmenu.prevent
      >
        <Button
          variant="ghost"
          size="sm"
          class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
          @click="handleContextMenuOpen"
        >
          打开章节
        </Button>
        <Button
          variant="ghost"
          size="sm"
          class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
          @click="handleContextMenuRename"
        >
          重命名章节
        </Button>
        <Button
          variant="ghost"
          size="sm"
          class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-stone-700 dark:text-zinc-200"
          @click="handleContextMenuToggleScope"
        >
          {{ contextMenuChapterInScope ? '移出流程范围' : '加入流程范围' }}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          class="h-auto w-full justify-start px-2 py-1.5 text-left text-xs text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-300 dark:hover:bg-red-900/20 dark:hover:text-red-200"
          @click="handleContextMenuDelete"
        >
          删除章节
        </Button>
      </div>
    </Teleport>
  </AppLayout>
</template>



